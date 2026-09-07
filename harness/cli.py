"""python -m harness "task description" -- runs one on-demand harness task.

    python -m harness "summarize why we picked F: as the drive root"
"""
from __future__ import annotations

import sys

from aiserver import LLM, load_config

from . import skills  # noqa: F401  (importing registers knowledge, coder)
from .loop import run
from .policy import OnDemandReadOnly


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print('Usage: python -m harness "task description"', file=sys.stderr)
        return 1
    task = " ".join(args)
    cfg = load_config()
    answer = run(task, LLM(cfg), OnDemandReadOnly(), out_dir=cfg.out / "harness" / "runs")
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
