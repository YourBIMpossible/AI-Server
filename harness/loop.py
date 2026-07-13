"""The turn loop: build the skill catalog and system prompt, call the model,
dispatch tool calls, feed results back, repeat until a final answer or
MAX_TURNS. Every step is recorded to the run's Transcript."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from aiserver import LLM
from aiserver.prompts import HARNESS_SYSTEM, render

from .policy import RunPolicy
from .registry import REGISTRY, ValidationError, validate_args
from .transcript import Transcript

MAX_TURNS = 8


def _skill_catalog() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": s.name, "description": s.description, "parameters": s.schema},
        }
        for s in REGISTRY.values()
    ]


def _system_prompt() -> str:
    names = ", ".join(sorted(REGISTRY)) or "(none registered)"
    return render(HARNESS_SYSTEM, skills=names, max_turns=str(MAX_TURNS))


def run(
    task: str,
    llm: LLM,
    policy: RunPolicy,
    *,
    out_dir: Path,
    run_id: str | None = None,
) -> str:
    run_id = run_id or uuid.uuid4().hex[:12]
    transcript = Transcript(Path(out_dir) / run_id / "transcript.jsonl")
    transcript.run_started(run_id, task)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": task},
    ]
    tools = _skill_catalog()
    try:
        for turn in range(1, MAX_TURNS + 1):
            reply = llm.chat_message(messages, tools=tools)
            transcript.model_reply(turn, reply.content, [tc.name for tc in reply.tool_calls])
            if not reply.tool_calls:
                answer = (reply.content or "").strip()
                transcript.run_finished(turn, answer)
                return answer
            messages.append({
                "role": "assistant",
                "content": reply.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in reply.tool_calls
                ],
            })
            for tc in reply.tool_calls:
                messages.append(_dispatch(tc, llm, policy, transcript, turn))
        transcript.run_aborted_max_turns(MAX_TURNS)
        return f"Did not converge within {MAX_TURNS} turns."
    finally:
        transcript.close()


def _dispatch(tc, llm: LLM, policy: RunPolicy, transcript: Transcript, turn: int) -> dict[str, Any]:
    skill_cls = REGISTRY.get(tc.name)
    if skill_cls is None:
        error = f"unknown skill {tc.name!r}"
        transcript.validation_failed(turn, tc.name, error)
        return {"role": "tool", "tool_call_id": tc.id, "content": f"Error: {error}"}
    if tc.parse_error:
        transcript.validation_failed(turn, tc.name, tc.parse_error)
        return {"role": "tool", "tool_call_id": tc.id, "content": f"Error: {tc.parse_error}"}
    skill = skill_cls(llm)
    try:
        validate_args(skill.schema, tc.arguments)
    except ValidationError as e:
        transcript.validation_failed(turn, tc.name, str(e))
        return {"role": "tool", "tool_call_id": tc.id, "content": f"Error: invalid arguments -- {e}"}
    if not policy.may_auto_run(skill, tc.arguments):
        transcript.policy_blocked(turn, tc.name, tc.arguments)
        return {
            "role": "tool", "tool_call_id": tc.id,
            "content": "Error: this action requires approval, which hasn't been granted.",
        }
    transcript.tool_called(turn, tc.name, tc.arguments)
    result = skill.run(**tc.arguments)
    transcript.tool_result(turn, tc.name, result.content, result.metadata)
    return {"role": "tool", "tool_call_id": tc.id, "content": result.content}
