"""python -m scout / run-scout -- read-only repo investigation with the local model.

    python -m scout --repo ../some-repo --task "Add a --json flag to the export command"
    python -m scout --repo . --task-file task.md --source notes.md --check "tests=python -m pytest --collect-only -q"
    python -m scout --repo . --task "..." --dry-run      # prepare prompts + seed evidence, no model call

Exit codes: 0 ok · 1 model/endpoint error · 2 usage or sandbox error · 4 the model's answer
was not parseable JSON (artifacts still written, with the raw answer alongside).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from aiserver import LLMError, load_config

from .run import DEFAULT_MAX_TURNS, ScoutInputs, run_scout
from .sandbox import SandboxError


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "task"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run-scout", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True, type=Path, help="target repository root (read-only)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--task", help="task description")
    g.add_argument("--task-file", type=Path, help="file containing the task description")
    p.add_argument("--source", action="append", default=[], type=Path, metavar="FILE",
                   help="extra text input (log, diff, acceptance criteria); repeatable")
    p.add_argument("--check", action="append", default=[], metavar="NAME=CMD",
                   help="allowlist one read-only validation command the model may run by NAME; repeatable")
    p.add_argument("--out", type=Path, help="output directory (default: <OUT>/scout/<timestamp>-<slug>)")
    p.add_argument("--dry-run", action="store_true", help="prepare prompts and seed evidence without calling the model")
    p.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        task = args.task if args.task is not None else args.task_file.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: cannot read task file: {e}", file=sys.stderr)
        return 2
    cfg = load_config()
    out_dir = args.out or (cfg.out / "scout" / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{_slug(task)}")
    inputs = ScoutInputs(repo=args.repo, task=task, out_dir=out_dir, sources=tuple(args.source),
                         checks=tuple(args.check), dry_run=args.dry_run, max_turns=max(1, args.max_turns))
    try:
        result = run_scout(inputs, cfg)
    except SandboxError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"error: model call failed: {e}", file=sys.stderr)
        return 1
    print(f"scout artifacts: {result.out_dir}")
    for p in result.artifacts:
        print(f"  {p.name}")
    if not args.dry_run and not result.parsed:
        print("warning: the model's final answer was not a JSON object; see raw-answer.txt and transcript.jsonl", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
