"""run-job entry point: dispatch a named automation.

    python -m automation <job>     # run a job
    python -m automation list       # list registered jobs
    run-job <job>                   # same, when the package is installed

Importing the job modules below registers them (see _framework.register).
"""
from __future__ import annotations

import sys

from aiserver import LLMError

from . import (  # noqa: F401  (register on import)
    daily_digest,
    decision_drift,
    revit_weekly,
    weekly_rollup,
)
from ._framework import job_names, run_job


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(f"Usage: python -m automation <job> | list\nJobs: {', '.join(job_names())}")
        return 0
    name = args[0]
    if name == "list":
        for n in job_names():
            print(n)
        return 0
    try:
        path = run_job(name)
    except KeyError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    print(f"[OK] {name}: wrote {path}")
    return 0
