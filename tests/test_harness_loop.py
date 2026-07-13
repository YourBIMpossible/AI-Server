"""harness/loop.py: the turn loop -- happy path, max-turns abort, invalid-args
recovery, empty-response failure."""
import json
from pathlib import Path

import pytest

from aiserver import LLM, LLMError, load_config
from conftest import _running, _sequenced_server
from harness.loop import MAX_TURNS, run
from harness.policy import OnDemandReadOnly
from harness.registry import REGISTRY, Skill, SkillResult, register

REPO = Path(__file__).resolve().parent.parent


@register
class _EchoSkill(Skill):
    name = "echo"
    description = "echoes back its input"
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def run(self, *, text: str) -> SkillResult:
        return SkillResult(content=f"echo: {text}")


def _llm(url, tmp_path):
    cfg = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"OLLAMA_HOST": url, "OUT": str(tmp_path / "out")},
    )
    return LLM(cfg, retries=0)


def _tool_call_body(name, arguments):
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": name, "arguments": json.dumps(arguments)}}
                ],
            }
        }]
    }


def _final_body(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_happy_path_tool_call_then_final_answer(tmp_path):
    srv, handler = _sequenced_server([
        (200, _tool_call_body("echo", {"text": "hi"})),
        (200, _final_body("done")),
    ])
    with _running(srv) as url:
        answer = run("say hi", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=tmp_path / "runs")
    assert answer == "done"
    assert handler.calls == 2


def test_max_turns_abort_when_model_never_stops_calling_tools(tmp_path):
    srv, handler = _sequenced_server([(200, _tool_call_body("echo", {"text": "again"}))])
    with _running(srv) as url:
        answer = run("loop forever", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=tmp_path / "runs")
    assert f"{MAX_TURNS} turns" in answer
    assert handler.calls == MAX_TURNS


def test_invalid_args_recorded_and_loop_recovers(tmp_path):
    srv, handler = _sequenced_server([
        (200, _tool_call_body("echo", {})),  # missing required 'text'
        (200, _final_body("recovered")),
    ])
    with _running(srv) as url:
        run_dir = tmp_path / "runs"
        answer = run(
            "try echo", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=run_dir, run_id="r1"
        )
    assert answer == "recovered"
    assert handler.calls == 2
    lines = (run_dir / "r1" / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert any(e["event"] == "validation_failed" for e in events)


def test_empty_response_raises_llmerror(tmp_path):
    srv, handler = _sequenced_server([(200, {"choices": [{"message": {"role": "assistant", "content": ""}}]})])
    with _running(srv) as url:
        with pytest.raises(LLMError):
            run("say nothing", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=tmp_path / "runs")


def test_unknown_skill_name_is_recorded_and_recoverable(tmp_path):
    srv, handler = _sequenced_server([
        (200, _tool_call_body("does_not_exist", {})),
        (200, _final_body("recovered")),
    ])
    with _running(srv) as url:
        run_dir = tmp_path / "runs"
        answer = run(
            "call a bogus tool", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=run_dir, run_id="r2"
        )
    assert answer == "recovered"
    lines = (run_dir / "r2" / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert any(e["event"] == "validation_failed" and "does_not_exist" in e["error"] for e in events)
