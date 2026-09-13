# AI-Server — Claude Code guide

Project: a portable, fully-local LLM inference + automation platform. Dev on the current rig
(RTX 5080, 16GB); relocates to a dedicated box (i9-14900K / RTX 3090 24GB / 4TB NVMe) by
pointing `INFERENCE_BASE_URL` in `.env` at the box (the serving-layer environment on the box
is a separate, non-optional step — see `relocate.md`). See `PROGRAM_PLAN.md` for the program
and `handoffs/` for per-work-package specs.

## The contract

What this project requires is **a private, stable, OpenAI-compatible local inference
endpoint**. Which program serves it is a deployment choice, not the mission. **Ollama is the
initial baseline runner**, not a decision — it stays under evaluation against llama.cpp
(`handoffs/WP-H_runner-bakeoff.md`), and nothing is permanent until it wins that test.

So: no runner name in application code, in config key names, or in an automation. Clients get
`INFERENCE_BASE_URL` / `INFERENCE_API_KEY` / `INFERENCE_MODEL` and nothing else. Runner-native
calls (`/api/ps`, `ollama pull`) are allowed only in ops tooling under `scripts/`, and only as
best-effort enrichment that degrades cleanly when the runner changes.

## Target box (2026-09-11: powered on, OS install pending)

i9-14900K / RTX 3090 24GB / 4 drives (layout TBD). Fully local, no external LLM calls.
**vLLM is not planned** — Ampere has no FP8 hardware, and the workload is single-user, so its
continuous-batching advantage has nothing to bite on. Planned one-DB-per-drive layout:
PostgreSQL + TimescaleDB (relational + time series) · Qdrant (vectors/RAG) · model storage
(GGUF/safetensors) · MongoDB or SQLite (logs, cold storage, BIM exports). See
`decisions/2026-09-10__box-build-reassessment.md`.

## House style (canonical)

Follow `F:\Claude-Profile\docs\system\WORKING-STYLE.md` and `F:\Claude-Profile\docs\system\SYSTEM-RULES.md`.

- Build exactly the work package asked; flag a worthwhile scope expansion in one line, don't add it silently.
- Optimization priority: correctness → security → performance → simpler architecture.
- Tests + the handoff's acceptance criteria are the definition of done.

## Project conventions

- **Portability is a hard constraint.** Anything that differs between the rig and the box goes in `.env` or `config/`. No hard-coded hosts, paths, or model names in code.
- **Runtime-agnostic.** Talk to the model only through the OpenAI-compatible API (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`), via `aiserver.client.LLM` — the one place the HTTP contract lives. Never shell out to the `ollama` CLI from application code. "OpenAI-compatible" is a claim to test, not a guarantee: chat templates, tool-call serialization, JSON-schema constraint, streaming, tokenization and error shapes all differ between runners.
- **Config.** Read via the `aiserver` package loader (WP-A). Don't re-implement `.env` parsing per script.
- **Deps.** Stdlib-first; a small pinned set is allowed (declare in `pyproject.toml`). No heavy frameworks without a one-line justification.
- **Outputs** go to `out/` (gitignored). **Never** write into `AI-Brain-Data/` or `BIMpossible_Workspace/` from an automation unless explicitly told — those are read-only sources.
- **Endpoint security.** LAN/Tailscale only; never bind a public interface in committed config.

## Layout

See `README.md`. Code: `aiserver/` (package), `automation/` (jobs), `rag/` (WP-B),
`scripts/` (setup), and a Dashboard tab in the AI-Dev Dashboard repo (WP-D). Tests in `tests/`.

## Validate

`python -m pytest` for unit tests; `scripts/smoke-test.py` against a running endpoint; each
handoff lists its own acceptance check. Tests must pass against a stdlib mock endpoint — no
real Ollama required in CI.
