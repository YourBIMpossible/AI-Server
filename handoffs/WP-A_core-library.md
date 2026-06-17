# WP-A — Core library (`aiserver/`)

**Goal:** a small, well-tested Python package that every automation and the RAG layer
imports, replacing the inline `.env` loaders and ad-hoc HTTP calls in the current scripts.

## Status (2026-06-16) — skeleton already scaffolded

The `aiserver/` package is scaffolded and its tests pass: `config.py` (merge order + overrides),
`client.py` (`chat` + `embed` against a mock endpoint, retries, endpoint-down error), `prompts.py`
(digest + rollup), `log.py`, plus `pyproject.toml` and `tests/`. Confirm with
`PYTHONPATH=. python -m pytest -q`. **Remaining WP-A work:** refactor `scripts/smoke-test.py` and
`automation/daily_digest.py` to import `aiserver` (drop their inline loaders), use `prompts.DIGEST`
and `log.get_logger`, and keep behaviour identical.

## Context (already in the repo)

- `scripts/smoke-test.py` and `automation/daily_digest.py` each inline a `.env` loader and
  raw `urllib` calls to `/v1/chat/completions`. That duplication is the thing to fix.
- Config keys are defined in `.env.example`: `OLLAMA_HOST`, `MODEL`, `EMBED_MODEL`,
  `WORKSPACE`, `OUT`, `DIGEST_DAYS`.

## Deliverables

- `pyproject.toml` — package `aiserver`, Python ≥3.10, minimal pinned deps.
- `aiserver/__init__.py`
- `aiserver/config.py` — load `.env` from repo root + environment overrides; typed accessors
  with defaults; a `Config` dataclass.
- `aiserver/client.py` — `LLM` class with `.chat(messages, model=None, **opts) -> str` and
  `.embed(texts, model=None) -> list[list[float]]`, both against the OpenAI-compatible API;
  timeout, retry-with-backoff, and a clear error when the endpoint is down.
- `aiserver/prompts.py` — named prompt templates (seed with the digest prompt).
- `aiserver/log.py` — structured run logging to `out/logs/`.
- `tests/test_config.py`, `tests/test_client.py` — `test_client` runs against a stdlib mock
  HTTP server (no real Ollama), mirroring the existing end-to-end test in the repo history.
- Refactor `scripts/smoke-test.py` and `automation/daily_digest.py` to import `aiserver`
  (behaviour unchanged).

## Acceptance

- `python -m pytest` green, including a mock-endpoint chat **and** embeddings test.
- `smoke-test.py` and `daily_digest.py` behave identically to before but contain no inline
  `.env`/HTTP code.
- No hard-coded host/model/paths outside `config.py` defaults.

## Constraints

Stdlib + minimal pinned deps only (`httpx` optional; `urllib` is fine). Portability per
`CLAUDE.md`. Don't change the `.env` schema without noting it in `.env.example` and here.

## Out of scope

RAG, new automations (WP-B / WP-C).
