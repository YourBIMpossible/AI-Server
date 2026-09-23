# WORKLOG

Routed items that fall outside the active NORTHSTAR mission. See `CLAUDE.md` / the north-star
protocol for the three-door rule this file exists to serve.

## Done

- **2026-09-16 — Box state check.** Read-only survey of `mybuddy` after the 09-13 closeout,
  recorded in `decisions/2026-09-16__box-state-and-chat-uis.md`. Endpoint still meets
  the closeout bar; model currently cold (per-request `keep_alive` from the owner's benchmark
  overrode the server default); three chat UIs found under `~/mybuddy/`, all
  localhost-only; four unevaluated models pulled 09-13.
- **2026-09-16 — Handoff validated.** The owner's `handoffs/MYBUDDY-HANDOFF-2026-09-16.md`
  (imported verbatim) checked against the box: `decisions/2026-09-16__handoff-validation.md`.
  Confirmed the loopback binds, compose gateway pins, `/srv` ownership, keep-alive override.
  Corrected: `gemma3:31b` → `gemma4:31b`, sizes were param counts, rig already has key auth
  (`ssh mybuddy`), gateway `:11440` absent from its picture. UFW rules and `docker ps`
  unverifiable without sudo.

- **2026-09-21 — Personal-AI handoff routed.** `handoffs/PERSONAL-AI-HANDOFF-2026-09-21.md`
  (verbatim) routed in `decisions/2026-09-21__personal-ai-and-pr671-ci-plan.md`. The PR #671
  CI-plan decision moved to the private BIMpossible repo.

- **2026-09-21 — Personal plan adopted; PR #21 replaced.** Owner approved the updated
  personal plan and history option (a): #21 closed unmerged, clean records re-submitted.

- **2026-09-21 — Plan steps 2–5 done.** All three UIs are pinned to
  `gemma4:26b-a4b-it-q4_K_M` with keep-alive forever:
  - Open WebUI: model list and defaults in its config DB.
  - AnythingLLM: compose env.
  - LibreChat: new `librechat.yaml` custom endpoint.

  Backups `*.bak-20260921` sit next to each file. Scoring (UIs stopped) kept gemma4:
  `decisions/2026-09-21__model-scoring-qwen3.5-9b.md`. New tools: `scripts/mybuddy-status`
  (box) and `scripts/windows/` (the desktop "MyBuddy" shortcut).

- **2026-09-21 — LibreChat reaches the model.** A new UFW rule, added by the owner:
  - The rule: `allow in on <LibreChat bridge> from 172.20.0.0/16 to 172.17.0.1 port 11434 proto tcp`,
    comment "LibreChat to Ollama". It is scoped to that bridge, that subnet and the Docker
    host-gateway address. Backup: `/root/ufw-backup-20260921.tgz`.
  - Verified from inside the container: the model list includes gemma4, and a chat on
    `gemma4:26b-a4b-it-q4_K_M` replied. All three UIs return 200, and `mybuddy-status` shows all
    online and the model loaded.
  - If Docker recreates `app_default`, the bridge name changes and the rule needs re-adding.
- **2026-09-22 — Open WebUI 0.11.3 → 0.11.4; "pilot" removed from box paths.**
  - The UI setup moved from `~/mybuddy-pilot` to `~/mybuddy`, and its data from
    `/srv/data/mybuddy-pilot` to `/srv/data/mybuddy`. The three compose files were repointed.
    Compose project names are unchanged, so the named volumes and the UFW bridge are untouched.
  - Backup of all UI data taken while stopped: `~/mybuddy-ui-backup-20260922.tgz` (874 MB).
  - `mybuddy-status`: all online, model loaded, exit 0.
  - Open WebUI still tracks `:main` (the dev branch); pinning a release tag is optional.
- **2026-09-22 — Box `WORKSPACE` set.** The box `.env` carried only `INFERENCE_MODEL`, so
  `load_config()` fell back to the Windows default `F:\BIMpossible-Workspace` — a path that can
  never exist there, which made every job's "roots not found" message misleading. The box `.env`
  (still mode 600) now sets `WORKSPACE=/home/zetard/workspace`, and that directory exists.
  `load_config()` on the box resolves it, and `workspace.exists()` is true. The flag raised in
  `decisions/2026-09-13__northstar-closeout-check.md` is cleared.
  - **No sources were copied.** The digest/rollup/drift jobs look for
    `BIMpossible_Workspace/01_BuildLog` and `AI-Brain-Data/decision-log` under that root; neither
    is on the box, so those jobs still report `workspace-roots-not-found` — now against a real box
    path. Populating it is a separate call, gated by the no-client-data policy.

## Roadmap

- **Build the AI-Server dashboard status card.** Repo: `F:\AI-Dashboard\Dashboard` (the live
  site — not the stale `F:\AI-Dev\Dashboard` copy, which predates the 2026-08 migration and
  is out of scope). Today the dashboard only carries a generic phase-progress row for
  "aiserver" (`data.js` ~line 1131); no dedicated widget shows endpoint up/down, loaded
  models, or the last digest/rollup/drift job results. The backend helper this card would
  call already exists and is merged: `F:\AI-Server\scripts\aiserver_status.py` (PR #5,
  `a7c8724`). Confirmed 2026-09-13 with the `ai-dashboard-80` session (owns the live repo):
  no work in flight on this, no collision risk. Scope: new `aiserver.js` panel + a card in
  `index.html`, sourced via `data.js` per `REFRESH-SPEC.md`'s existing pattern (verify that
  spec's own aiserver section against the live repo before building — the old AI-Dev copy's
  version pointed at a dead path). Not part of the AI-Server NORTHSTAR mission (that mission
  is the endpoint, not its dashboard surface) — build it as its own task, in the dashboard
  repo, whenever picked up.
- **Residency after scoring or benchmarks.** Anything that loads another model can evict
  gemma4. `mybuddy-status` shows "not loaded"; the next UI chat reloads it. A timer-based
  re-warm is optional; add it only if cold starts annoy.

- **RAG source governance before any ingest.** `config/rag_sources.txt` declares
  `F:\AI-Brain-Data` and `F:\BIMpossible-Workspace` whole; nothing is ingested yet. Write the
  approved roots, exclusions (client data categorically?), citation rule and re-index/delete
  behaviour before the first index run.
- **Local-model behavioural lane for BIMpossible CI (cross-repo).** A local-provider eval runner
  with its own evidence, never labelled as provider evidence. New consumer of `mybuddy`; needs
  its own scope before building. Details live in the private BIMpossible repo.

## Needs your call

Nothing open. The four earlier calls (UI placement, Goose, scope split, raw `:11434`) were
settled 2026-09-21 by the adopted personal plan `plans/2026-09-21__mybuddy-ai-server-plan.md`:
UIs stay on the box; Goose/agents and a separate workspace project are parked; `:11434` is
accepted for the private setup and revisited on the plan's listed triggers.
