"""Append-only, event-typed JSONL run transcript. Each line is one event,
written and flushed immediately so a crash mid-run still leaves a usable
trace, not a raw dump of the OpenAI-shaped messages array."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Transcript:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def _write(self, event: str, **fields: Any) -> None:
        self._fh.write(json.dumps({"event": event, **fields}) + "\n")
        self._fh.flush()

    def run_started(self, run_id: str, task: str) -> None:
        self._write("run_started", run_id=run_id, task=task)

    def model_reply(self, turn: int, content: str | None, tool_call_names: list[str]) -> None:
        self._write("model_reply", turn=turn, content=content, tool_calls=tool_call_names)

    def tool_called(self, turn: int, skill: str, args: dict[str, Any]) -> None:
        self._write("tool_called", turn=turn, skill=skill, args=args)

    def tool_result(self, turn: int, skill: str, content: str, metadata: dict[str, Any] | None) -> None:
        self._write("tool_result", turn=turn, skill=skill, content=content, metadata=metadata)

    def validation_failed(self, turn: int, skill: str, error: str) -> None:
        self._write("validation_failed", turn=turn, skill=skill, error=error)

    def policy_blocked(self, turn: int, skill: str, args: dict[str, Any]) -> None:
        self._write("policy_blocked", turn=turn, skill=skill, args=args)

    def run_finished(self, turns: int, final_answer: str) -> None:
        self._write("run_finished", turns=turns, final_answer=final_answer)

    def run_aborted_max_turns(self, turns: int) -> None:
        self._write("run_aborted_max_turns", turns=turns)

    def close(self) -> None:
        self._fh.close()
