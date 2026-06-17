# AI-Server — Claude Code guide

Project: a portable, fully-local LLM inference + automation platform. Dev on the current rig
(RTX 5080, 16GB); relocates to a dedicated box (i9-14900K / RTX 3090 24GB / 4TB NVMe) by
changing `OLLAMA_HOST` in `.env`. See `PROGRAM_PLAN.md` for the program and `handoffs/` for
per-work-package specs.

## House style (canonical)

Follow `F:\AI-Dev\system\WORKING-STYLE.md` and `F:\AI-Dev\system\SYSTEM-RULES.md`.

- Build exactly the work package asked; flag a worthwhile scope expansion in one line, don't add it silently.
- Optimization priority: correctness → security → performance → simpler architecture.
- Tests + the handoff's acceptance criteria are the definition of done.

## Project conventions

- **Portability is a hard constraint.** Anything that differs between the rig and the box goes in `.env` or `config/`. No hard-coded hosts, paths, or model names in code.
- **Runtime-agnostic.** Talk to the model only through the OpenAI-compatible API (`/v1/chat/completions`, `/v1/embeddings`). Never shell out to the `ollama` CLI from application code.
- **Config.** Read via the `aiserver` package loader (WP-A). Don't re-implement `.env` parsing per script.
- **Deps.** Stdlib-first; a small pinned set is allowed (declare in `pyproject.toml`). No heavy frameworks without a one-line justification.
- **Outputs** go to `out/` (gitignored). **Never** write into `AI-Brain-Data/` or `BIMpossible_Workspace/` from an automation unless explicitly told — those are read-only sources.
- **Endpoint security.** LAN/Tailscale only; never bind a public interface in committed config.

## Layout

See `README.md`. Code: `aiserver/` (package), `automation/` (jobs), `rag/` (WP-B),
`scripts/` (setup), and a Dashboard tab under `F:\AI-Dev\Dashboard\` (WP-D). Tests in `tests/`.

## Validate

`python -m pytest` for unit tests; `scripts/smoke-test.py` against a running endpoint; each
handoff lists its own acceptance check. Tests must pass against a stdlib mock endpoint — no
real Ollama required in CI.
