"""harness/transcript.py: typed, append-only JSONL event log."""
import json

from harness.transcript import Transcript


def test_events_are_written_as_typed_jsonl_lines(tmp_path):
    path = tmp_path / "run" / "transcript.jsonl"
    t = Transcript(path)
    t.run_started("r1", "do the thing")
    t.model_reply(1, "thinking", ["echo"])
    t.tool_called(1, "echo", {"text": "hi"})
    t.tool_result(1, "echo", "echo: hi", None)
    t.validation_failed(2, "echo", "missing required argument 'text'")
    t.policy_blocked(3, "echo", {"text": "hi"})
    t.run_finished(3, "done")
    t.close()

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    events = [line["event"] for line in lines]
    assert events == [
        "run_started",
        "model_reply",
        "tool_called",
        "tool_result",
        "validation_failed",
        "policy_blocked",
        "run_finished",
    ]
    assert lines[0]["run_id"] == "r1"
    assert lines[2]["skill"] == "echo"
    assert lines[2]["args"] == {"text": "hi"}


def test_run_aborted_max_turns_event(tmp_path):
    path = tmp_path / "run2" / "transcript.jsonl"
    t = Transcript(path)
    t.run_aborted_max_turns(8)
    t.close()
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert line == {"event": "run_aborted_max_turns", "turns": 8}


def test_parent_directory_is_created(tmp_path):
    path = tmp_path / "nested" / "dir" / "transcript.jsonl"
    t = Transcript(path)
    t.run_started("r1", "task")
    t.close()
    assert path.exists()


def test_event_is_visible_before_close(tmp_path):
    path = tmp_path / "run" / "transcript.jsonl"
    t = Transcript(path)
    t.run_started("r1", "task")
    # Read via the same path while `t` is still open (no close() yet) -- this only
    # passes if _write() flushes immediately, since close() is what would normally
    # force the OS buffer out.
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line == {"event": "run_started", "run_id": "r1", "task": "task"}
    t.close()
