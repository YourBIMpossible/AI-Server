# WP-B — RAG / knowledge layer (`rag/`)

**Goal:** local retrieval over your own docs — ask questions and detect drift, fully on-box.
**Depends on:** WP-A (`aiserver`).

## Sources to index (read-only)

- `AI-Brain-Data/` — decision-log, standards-and-refs, _reference, prompts-i-use, etc.
- `BIMpossible_Workspace/` — 00_Strategy, 01_BuildLog, 02_Reference.

Make the source roots configurable via `config/rag_sources.txt` (one path per line).

## Stack (locked)

`sqlite-vec` vector store (single file at `out/rag/index.db`); embeddings via
`aiserver.client.LLM.embed` using `EMBED_MODEL` (nomic-embed-text) on the same endpoint.

## Deliverables

- `rag/ingest.py` — walk sources, chunk (~800 tokens, small overlap), embed, upsert into
  sqlite-vec with metadata (path, mtime, heading). **Incremental:** skip unchanged files by
  mtime/hash; report new/changed/removed counts.
- `rag/query.py` — CLI: `python -m rag.query "question"` → top-k chunks + a synthesized answer
  with **citations (file path + heading)**; must refuse to answer beyond retrieved text.
- `rag/drift.py` — for each `decision-log/` entry, retrieve the most relevant canonical doc;
  flag decisions with no strong match (candidate undocumented decisions). Write
  `out/rag/drift-YYYY-MM-DD.md`. (Implements the want in `system/HOW-I-WORK.md`.)
- `tests/` — ingest a tiny temp corpus; assert a known query returns the right chunk; drift
  flags a seeded undocumented decision and does not flag a well-documented one.

## Acceptance

- Fresh ingest of the real vault completes; re-running is incremental (near-instant, 0 new).
- A known question (e.g., "why F: drive as root?") returns the right decision-log entry with a
  citation.
- Drift report surfaces a seeded discrepancy without flagging well-documented decisions.

## Constraints

Read-only on the sources; outputs only under `out/`. Chunker and store must behave identically
on Windows and Linux (portability per `CLAUDE.md`).

## Out of scope

A web UI (CLI/API only for now); generation-quality tuning beyond citations.
