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


@register
class _BoomSkill(Skill):
    name = "boom"
    description = "deliberately raises to exercise tool_failed handling"
    schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> SkillResult:
        raise RuntimeError("boom: deliberate failure")


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


def test_extra_undeclared_arg_is_filtered_before_dispatch(tmp_path):
    """validate_args() deliberately lets undeclared extra keys pass (matches JSON
    Schema's additionalProperties:true default). Before this fix, that extra key
    would reach skill.run(**tc.arguments) and blow up with an uncaught TypeError
    (echo's run() is keyword-only on `text`). The fix filters dispatch args down
    to the skill's declared schema properties first, so the extra key never
    reaches run() at all -- the skill executes normally and the run reaches a
    final answer, proving the filter (not just validate_args tolerance)."""
    srv, handler = _sequenced_server([
        (200, _tool_call_body("echo", {"text": "hi", "extra": "nope"})),
        (200, _final_body("done")),
    ])
    with _running(srv) as url:
        run_dir = tmp_path / "runs"
        answer = run(
            "say hi", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=run_dir, run_id="r3"
        )
    assert answer == "done"
    assert handler.calls == 2
    lines = (run_dir / "r3" / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    tool_called = next(e for e in events if e["event"] == "tool_called")
    assert tool_called["args"] == {"text": "hi"}
    assert tool_called["ignored_args"] == ["extra"]
    tool_result = next(e for e in events if e["event"] == "tool_result")
    assert tool_result["content"] == "echo: hi"


def test_skill_execution_error_recorded_as_tool_failed_and_loop_recovers(tmp_path):
    """A skill whose run() raises must not crash the whole run() loop -- that's
    exactly the "abort the whole run over one malformed/failing call" failure
    mode validation_failed exists to avoid. Confirms: (1) a distinct tool_failed
    event is recorded (not validation_failed, since dispatch itself was valid),
    and (2) the loop continues to a later turn and reaches a normal final answer
    instead of the exception propagating out of run()."""
    srv, handler = _sequenced_server([
        (200, _tool_call_body("boom", {})),
        (200, _final_body("recovered")),
    ])
    with _running(srv) as url:
        run_dir = tmp_path / "runs"
        answer = run(
            "trigger boom", _llm(url, tmp_path), OnDemandReadOnly(), out_dir=run_dir, run_id="r4"
        )
    assert answer == "recovered"
    assert handler.calls == 2
    lines = (run_dir / "r4" / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    failed = [e for e in events if e["event"] == "tool_failed"]
    assert len(failed) == 1
    assert failed[0]["skill"] == "boom"
    assert "boom" in failed[0]["error"]
    assert not any(e["event"] == "validation_failed" for e in events)
