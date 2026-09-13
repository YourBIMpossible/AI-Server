# Benchmark policy — when a full eval or runner bakeoff is rerun, and when it is not

**Date:** 2026-09-13 · **Box:** `mybuddy` · **Status:** policy (in force) · **Branch:** `claude/repo-scout`

WP-F (`2026-09-13__wp-f-eval-separates-models.md`) and WP-H (`2026-09-13__wp-h-runner-bakeoff.md`)
are complete. Their numbers stay valid until something that produced them changes. This note says
what counts as such a change, so that nobody — human, automation, or assistant session — reruns a
GPU-monopolising benchmark because a report looked stale or a reproduction seemed tidy.

## Triggers for a full eval (`python -m eval.run`) or a bakeoff (`scripts/bakeoff-session.sh`)

Exactly one of these must be true. If none is, the existing decision notes are the answer.

1. **Model or quantization change.** A different model tag, a different quant of the same model, a
   different GGUF blob for the same tag (`config/models.txt` changes, or `ollama pull` replaces the
   blob).
2. **Material runtime change.** Ollama, llama.cpp, CUDA, or the NVIDIA driver moves to a version
   that changes inference behaviour (new attention/KV paths, tokenizer or chat-template fixes,
   scheduler changes). A patch release with no inference-relevant notes is not material; record the
   reason either way in the run's decision note.
3. **Runtime setting change** that alters what a request sees: context length, KV cache dtype,
   parallelism (`OLLAMA_NUM_PARALLEL` / `-np`), flash attention, keep-alive, max loaded models.
   These are batch identity — see `eval/bakeoff/protocol.md`.
4. **Production serving incident** — a wrong answer, silent truncation, refusal, or latency
   regression seen by a real automation against the endpoint, that a targeted probe cannot
   attribute. The rerun is the diagnostic, scoped to the tier that failed first.
5. **New or changed eval cases or rubric** (`eval/cases.jsonl`, `eval/judge_calibration.jsonl`,
   `eval/automation_rubrics/`). Adding cases is itself a trigger: a report on main must have scored
   every case in the file it names.
6. **Explicit operator request**, in the operator's own words in the current session. A carried
   mandate, a memory, or a previous session summary is not a request.

## What never triggers a benchmark

- Normal usage: automations, RAG queries, harness runs, the repo scout, dictation cleanup.
- Reading, comparing or citing an old report. Staleness is a date, not a trigger.
- A reproduction that fails for an environment reason (see
  `2026-09-13__scheduled-acceptance-env-gap.md`). Fix the environment; do not re-measure.
- Curiosity about a model that is not a candidate in `config/models.txt`.
- Any automatic schedule. There is no timer, cron, or job that reruns eval or bakeoff, and none
  is to be added. Reruns are started by a person, under the GPU-work interlock
  (`aiserver/gpulock.py`, `scripts/gpu_lock.py`), and end with a decision note.

## What a rerun must produce

A `decisions/YYYY-MM-DD__<slug>.md` naming the trigger (one of 1–6), the batch identity
(model tag + blob digest, runner + version, driver, context/KV/parallelism), the commands run,
and the outcome. Raw artifacts stay under `out/` (gitignored); the note is canonical.

## Runner swaps

A runner swap is a deployment change (`NORTHSTAR.md`), never a side effect of usage. The
preflight for a deliberate swap is in `ops/PRODUCTION-CONTRACT.md`. Nothing in `automation/`,
`harness/`, `scout/` or `rag/` may start, stop or select a runner.
