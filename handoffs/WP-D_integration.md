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

- Convert the existing `revit-log-weekly-processor` to call the local endpoint via `aiserver`
  instead of Claude. Keep the Claude version side-by-side for one week (eval, WP-F) before
  cutover.
- **Acceptance:** the local version produces an equivalent weekly summary; cutover is a config
  flip.

## Constraints

Follow each target folder's own rules (`Dashboard/REFRESH-SPEC.md`, the PC-Monitor README).
Read-only where those tools are read-only.
