# pickup_checker

Standalone, isolated-venv tool. Not wired into `aiserver/`. See
`docs/superpowers/specs/2026-07-25-pdf-pickup-checker-design.md` in the parent repo for the
full design. Milestone 1 scope only: detection core + golden-set gate runner. No queue
persistence, no UI, no PDF export, no AI -- those are separate future plans.

## Setup
    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"

## Test
    .venv/Scripts/python.exe -m pytest -v
