# MyBuddy / AI-Server — forward plan

**Status:** proposed 2026-09-21. **Mission:** `NORTHSTAR.md` (active, locked) — one measurable
OpenAI-compatible local endpoint. **Closeout 2026-09-13: all 5 criteria met** (PR #20). This plan
is what comes after: keep the endpoint honest, settle the calls the pilot raised, then decide
whether a Personal AI Workspace becomes its own project.
**Sources:** `WORKLOG.md` (Roadmap + Needs your call),
`decisions/2026-09-16__box-state-and-chat-ui-pilot.md`,
`decisions/2026-09-16__handoff-validation.md`,
`decisions/2026-09-21__personal-ai-and-pr671-ci-plan.md` Part 2. PR #671 is planned separately
in `plans/2026-09-21__pr671-resolution-plan.md`.

## Current state (2026-09-16 survey, validated)

| Piece | State |
|---|---|
| Box | `mybuddy` — Ubuntu 26.04.1, RTX 3090 24 GB, LAN `192.168.1.128`, tailnet `100.89.51.34`, `ssh mybuddy` |
| Runner | Ollama 0.34 on `*:11434`, no auth (accepted at closeout) |
| Client door | Caddy gateway `:11440`, Bearer `INFERENCE_API_KEY` |
| Model pick | `gemma4:26b-a4b` (27/27 WP-F) in `config/models.txt` |
| Unscored models | `gemma4:31b-it-q4_K_M`, `qwen3.8:27b-q4_K_M`, `qwen3.5:9b`, `nemotron-3.5-lightning:30b-a3b-q4_K_M` |
| Chat-UI pilot | `~/mybuddy-pilot`: Open WebUI `:3000`, AnythingLLM `:3001`, LibreChat `:3080` — loopback-only, **bypassing the gateway** |
| Constraints | System Python 3.14, no pip/venv; docker/sudo need a PTY |
| PR #21 | Open, clean — this branch; carries the 09-16/09-21 records |

---

## Gate 0 — owner calls (block the phases that depend on them)

| # | Call | Options | Unblocks |
|---|---|---|---|
| G1 | **Pilot placement** | (a) keep on the box as an endpoint consumer · (b) move to the rig | Phase 2 |
| G2 | **Raw `:11434`** | keep as settled · reopen: rebind to loopback or UFW to gateway only | Phase 2 step 1 |
| G3 | **Scope split** | yes → draft `NORTHSTAR.personal-ai.draft.md` for you to lock · no → Phase 4 stays parked | Phase 4 |
| G4 | **Goose on the rig** | folds into G3's draft if yes; parked if no | Phase 4 |

Phase 1 needs none of these and can start now.

---

## Phase 1 — Keep the instrument honest (in-mission, no call needed)

1. **Merge PR #21** (records only). Then box housekeeping: fast-forward `~/AI-Server` to
   `origin/main`, re-run `setup-ops.sh` from `~/AI-Server` so gateway units leave the worktree
   path, prune merged box worktrees (`box-mission`, `box-phase0`, `box-wrapup`), move loose
   benchmark files out of `~`.
2. **Batch identity records pilot load** — add "pilot containers running: yes/no" (HTTP probe of
   `:3000/:3001/:3080`, no sudo) to eval batch identity; or evals run with the pilot stopped.
3. **Score the four unevaluated models** with `eval/` on the box, pilot stopped, batch identity
   recorded. `config/models.txt` changes only if a challenger beats gemma4 on WP-F.
4. **Scheduled-acceptance env gap** — WP-H scheduled acceptance under `systemd-run --user` uses
   system Python without `sqlite_vec`. Point it at the project interpreter; confirm one timer run.
5. **`mybuddy-status` / `-start` / `-stop`** in `scripts/` — plain-English health of runner,
   gateway, loopback UI ports via HTTP probes; container detail degrades cleanly without sudo.

**Exit:** PR #21 merged, four models scored with identity, one clean scheduled acceptance run.

## Phase 2 — Settle the pilot (after G1, G2)

1. **G2 = reopen:** rebind Ollama to `127.0.0.1:11434` (or UFW allow gateway only), re-verify
   `:11440` serves WP-F end-to-end, record in `decisions/`. G2 = settled: skip.
2. **Route every UI through `:11440`** with `INFERENCE_API_KEY` — no UI talks to raw `:11434`.
   LibreChat needs a `librechat.yaml` `custom` endpoint (none exists today); verify the
   `172.20.0.0/16` UFW allowance (root) first — current rules cover only `.18`/`.19`.
3. **Residency policy** — chat UIs send their own `keep_alive` and evict the working model.
   Pick: `preload.py` re-warms on a timer, or residency follows the last client. Record it.
4. **G1 = (a):** one-click launcher on the rig (background forwards, dedup, open
   `127.0.0.1:13000/13001/13080`, "box offline" message).
   **G1 = (b):** move the stack to the rig pointed at `:11440` over the LAN; tear down
   `~/mybuddy-pilot` on the box; launcher is moot.

**Exit:** no client bypasses the gateway; residency rule written; pilot where G1 put it.

## Phase 3 — Retrieval groundwork (in-mission prep, no ingest)

1. **RAG source governance doc** before any index run: approved roots (today
   `config/rag_sources.txt` lists `F:\AI-Brain-Data` and `F:\BIMpossible-Workspace` whole),
   exclusions, whether client data is categorically blocked (NORTHSTAR: no client data on the
   box until the OCR hard stop clears), citation rule, re-index/delete behaviour.
2. Narrow `config/rag_sources.txt` to what that doc approves.

**Exit:** governance doc committed; nothing ingested until it exists.

## Phase 4 — Personal AI Workspace (only if G3 = yes)

Drafted as `NORTHSTAR.personal-ai.draft.md` for the owner to lock — not built from this plan.
The draft would carry:

- `mybuddy` as infrastructure; the workspace as a consumer through `:11440` only.
- Cockpit UI choice (from the Phase 2 outcome).
- Goose on the rig in disposable worktrees, benchmarked on ~10 real tasks: local vs the current
  frontier workflow, same task set, scored.
- Cloud provider/routing policy (absent · manual user choice · automatic) — the endpoint stays
  fully local regardless.
- MCP/tool authority policy — one tool at a time, explicit permission boundary before shell,
  Git, browser, GitHub or Revit control.
- Curated RAG on the Phase 3 governance rules.

## Parked — not in this plan's path

| Item | Why parked |
|---|---|
| AI-Server dashboard status card (`F:\AI-Dashboard\Dashboard`) | Dashboard repo, not the mission; owner said hands off the UI until asked |
| Local-model behavioural lane for BIMpossible CI | Cross-repo new consumer; needs its own scope (see #671 plan) |
| Goose/agent harness **on the box** | Superseded by Goose-on-rig (G4) |
| vLLM | NORTHSTAR off-limits on Ampere/single-user; re-enters only if either stops being true |
| Customer-facing inference, bigger embedding model, GPU OCR rescue | NORTHSTAR out of scope |

## Standing rules

LAN/Tailscale only, never port-forward `11434` · no client data on the box · no runner name in
client code/config/automations · no rig numbers ported · not a desktop · NORTHSTAR files
human-only · automations never write into `AI-Brain-Data` or `BIMpossible_Workspace`.
