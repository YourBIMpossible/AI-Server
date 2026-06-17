# WP-C — Automation suite + job framework (`automation/`)

**Goal:** turn the one-off digest into a small framework so new local automations are
drop-in, and ship three useful jobs. **Depends on:** WP-A (WP-B for the drift job).

## Deliverables

- `automation/_framework.py` — a `Job` base (name, schedule hint, `run()` writes to
  `out/<job>/`), a registry, and a `run-job <name>` entry point. Jobs use `aiserver` (WP-A).
- Refactor `daily_digest.py` onto the framework (behaviour unchanged).
- `automation/weekly_rollup.py` — Monday roll-up of the week's BuildLog + decision-log into a
  status note (longer horizon than the daily digest).
- `automation/decision_drift.py` — thin scheduled wrapper over `rag/drift.py` (WP-B).
- `automation/register-tasks-windows.ps1` — register all jobs (daily digest 07:00, weekly
  rollup Mon 07:15, drift Sat 07:30); supersedes the single-task script.
- `tests/` — each job runs against a mock endpoint + temp workspace and writes expected output.

## Acceptance

- `run-job daily-digest`, `run-job weekly-rollup`, `run-job decision-drift` all produce files
  under `out/` against a mock endpoint.
- Adding a new job = drop a file subclassing `Job` + one registry line (document the pattern
  in the framework module docstring).

## Constraints

Jobs are read-only on the workspace; OS-agnostic Python logic, OS-specific only in the
register scripts.

## Out of scope

Email triage — needs Gmail API creds on the box (the Cowork Gmail connector can't be called
from a headless script). Separate, optional WP.
