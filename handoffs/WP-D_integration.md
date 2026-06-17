# WP-D — Integration with the existing stack

**Goal:** make the AI server visible and wired into what you already run. **Depends on:**
WP-A (WP-C for D1's job outputs). The three halves are independent — up to three sessions.

## D1 — Dashboard "AI Server" tab (`F:\AI-Dev\Dashboard\`)

- Add a tab/panel to the existing dashboard (`index.html` + a new `aiserver.js` + data in
  `data.js`). Show: endpoint up/down, models loaded (`GET /api/tags`), and the last
  digest/rollup/drift result + timestamp (read the newest files in `AI-Server/out/`).
- **Respect `Dashboard/REFRESH-SPEC.md`:** read-only refresh, only write `data.js`, terse
  one-line entries, no git mutations beyond the existing push step.
- **Acceptance:** the tab renders endpoint status + last-job summaries; a refresh updates it
  without touching `index.html`.

## D2 — PC-Monitor profile for the AI box (`F:\AI-Dev\PC-Monitor\`)

- PC-Monitor already reads `nvidia-smi`. Add a config profile / tag set for the inference box:
  process tags for `ollama`, per-process VRAM, and a "model loaded" gauge via `GET /api/ps`.
- Document deploying a second collector instance on the box (already a logon Scheduled Task —
  just a second install with the AI profile).
- **Acceptance:** PC-Monitor with the AI profile shows Ollama VRAM + an inference panel.

## D3 — Offload one real scheduled task

**Premise correction (2026-06-17).** The `revit-log-weekly-processor` does NOT call Claude/any
LLM — `AI-Brain-Data/Revit-AI/process_revit_logs.py` is a deterministic parser, and its live
task definition lives on `G:` (out of scope). So there is nothing to "convert from Claude," and
the original "equivalent summary + config-flip" acceptance was unsatisfiable as written.

**Chosen direction — writer-side engine flag (done in code, owner cutover owed):**
`process_revit_logs.py` grows `--engine deterministic|local` (default `deterministic`):
- `deterministic` — behaviour is exactly current (byte-identical templated weekly table; proven
  against the original function).
- `local` — reads the same inputs but has the local LLM write a narrative weekly summary at the
  **same canonical path** (`context/weekly-revit-summary.md`), grounded on the deterministic
  metrics, falling back to deterministic if the endpoint is unreachable (so the live job can't
  break).

- **Acceptance:** deterministic mode unchanged; local mode writes the weekly summary at the
  canonical path via the local endpoint. **Cutover = change the scheduled task's args to
  `--engine local`** (edit the G:-hosted `SKILL.md` "Execute:" line — owner action).
- Scoped relaxation of "AI-Server read-only on AI-Brain-Data": the AI-Brain-Data script itself
  may call the local LLM (OpenAI-compatible HTTP). The earlier parallel AI-Server `revit-weekly`
  job (PR #6 → `out/revit-weekly/`) was **removed** (reverted) — the writer-side `--engine` flag
  is the sole D3 path.

## Constraints

Follow each target folder's own rules (`Dashboard/REFRESH-SPEC.md`, the PC-Monitor README).
Read-only where those tools are read-only.
