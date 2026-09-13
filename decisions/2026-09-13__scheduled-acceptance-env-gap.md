# Scheduled acceptance ran under system Python — environment gap, not a regression

**Date:** 2026-09-13 · **Box:** `mybuddy` · **Class:** environment / reproducibility hardening ·
**Status:** follow-up (no product code changed) · **Branch:** `claude/repo-scout`

## What happened

Reproducing WP-H via `scripts/bakeoff-session.sh` over SSH reproduced every performance, probe and
WP-F number, but the **real-automation acceptance leg failed on both runners** with
`ModuleNotFoundError: No module named 'sqlite_vec'`.

Cause: `scheduled_acceptance()` launches `scripts/automation_acceptance.py` through
`systemd-run --user`, which resolved `${PYTHON:-python3}` to `/usr/bin/python3` — the system
interpreter, not the managed venv that carries the pinned `sqlite-vec>=0.1.9` dependency.
`automation/cli.py` imports every job at load time (register-on-import, by design), and
`decision_drift` → `rag.store` → `sqlite_vec`, so even `daily_digest`, which uses no RAG, cannot
start.

## Why this is not a finding against WP-H or the runner

The authoritative acceptance is `decisions/2026-09-13__wp-h-runner-bakeoff.md` (rubric v2, both
runners PASS), run by the box session in the proper environment. The reproduction failed before
any model was called; the failure is identical on both runners and independent of the endpoint.
Per `decisions/2026-09-13__benchmark-policy.md`, an environment failure is not a rerun trigger.

## Follow-up (when next touched — not done opportunistically)

1. `scripts/bakeoff-session.sh` and `scripts/automation_acceptance.py` should invoke the managed
   venv interpreter explicitly (resolve `$ROOT/.venv/bin/python` when present, else fail with a
   message) rather than `${PYTHON:-python3}`.
2. `scripts/automation_acceptance.py` should log `sys.executable` and run a dependency preflight
   (`import sqlite_vec`) before scheduling anything, so the failure names itself.
3. Do **not** install project dependencies into the box's system Python and do not refactor the
   register-on-import pattern to work around this.

None of this changes measured numbers; it changes whether the reproduction harness can run at all.
