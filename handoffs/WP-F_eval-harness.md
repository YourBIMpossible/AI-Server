# WP-F — Eval harness (local vs Claude)

**Goal:** make "offload to local" an evidence-based decision per task, not a guess.
**Depends on:** WP-A (B/C for real task fixtures).

## Deliverables

- `eval/cases.jsonl` — 15–20 labeled cases across your real task types: log digest, weekly
  rollup, RAG answer (with the expected source), and a couple of classification prompts. Each:
  `id`, `task`, `input`, `rubric` (what a good answer must contain).
- `eval/run.py` — run each case through (a) the local model and (b) a Claude baseline (Claude
  via API key if present, else mark "baseline skipped"); score against the rubric
  (keyword/contains + an optional model-graded pass/fail using the local model as judge is fine
  for v1).
- `eval/report.py` — write `out/eval/report-YYYY-MM-DD.md`: per-task local pass-rate, a
  **"local OK / route to Claude" recommendation table**, and the model + quant used.

## Acceptance

- `python -m eval.run` produces scores for every case against the local endpoint.
- The routing table is defensible: tasks where local clears the rubric threshold are marked
  "local OK," the rest "route to Claude."
- Re-runnable on the box's bigger model to re-certify before trusting a job there.

## Constraints

Deterministic where possible (temperature 0 for graded runs). No network calls except the two
endpoints. Don't hard-code the threshold — read `EVAL_PASS_THRESHOLD` from `.env` (default 0.8).
