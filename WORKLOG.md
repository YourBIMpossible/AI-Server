# WORKLOG

Routed items that fall outside the active NORTHSTAR mission. See `CLAUDE.md` / the north-star
protocol for the three-door rule this file exists to serve.

## Done

- **2026-09-16 — Box state check.** Read-only survey of `mybuddy` after the 09-13 closeout,
  recorded in `decisions/2026-09-16__box-state-and-chat-ui-pilot.md`. Endpoint still meets
  the closeout bar; model currently cold (per-request `keep_alive` from the owner's benchmark
  overrode the server default); three chat UIs found under `~/mybuddy-pilot/`, all
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
- **Score the four unevaluated models.** `gemma4:31b-it-q4_K_M`, `qwen3.8:27b-q4_K_M`,
  `qwen3.5:9b`, `nemotron-3.5-lightning:30b-a3b-q4_K_M` are on the box with no WP-F score.
  Run `eval/` on the box against each, with batch identity, so the pick in
  `config/models.txt` stays evidence-backed if any of them is meant to challenge gemma4.
  The owner's `~/ollama-benchmark.py` on nemotron is a smoke signal (fits, 22.7 GB peak), not
  a score.
- **Batch identity should record pilot load.** Add "pilot containers running: yes/no" to the
  eval batch identity, or run evals with `~/mybuddy-pilot` stopped, so LibreChat's permanent
  Mongo/Meilisearch/Postgres/RAG stack cannot silently skew a measurement.
- **Residency policy vs chat UIs.** Chat front-ends send their own `keep_alive` and evict the
  preloaded working model. Decide whether `preload.py` should re-warm on a timer, or whether
  residency is simply left to whichever client spoke last.
- **LibreChat has no chat endpoint configured.** No `librechat.yaml` exists or is mounted;
  Ollama is wired for embeddings only. If LibreChat stays in the pilot it needs a `custom`
  endpoint pointing at the box's OpenAI-compatible URL (ideally through the `:11440` gateway
  with `INFERENCE_API_KEY`, not raw `:11434`).
- **One-click UI access from the rig (handoff Priority 1).** Key auth already works
  (`ssh mybuddy`); what's left is a launcher (`scripts/` or the rig) that starts the three
  forwards in the background, dedups, opens `127.0.0.1:13000/13001/13080`, and reports "box
  offline". Do after the pilot-placement call below — moot if the pilot moves to the rig.
- **`mybuddy-status` / `-start` / `-stop` (handoff Priority 2).** Plain-English health for
  Ollama, gateway, containers, loopback ports. Fits `scripts/` as ops tooling; container
  checks need sudo on the box (deliberate), so status should degrade to HTTP probes.
- **LibreChat network allowance.** `app_default` is `172.20.0.0/16`; the handoff's two UFW
  rules cover only `.18` and `.19`. Verify (root) before wiring a LibreChat endpoint.
- **Box housekeeping.** Fast-forward `~/AI-Server` to `origin/main` (`c578e69`); prune the
  merged box worktrees (`box-mission`, `box-phase0`, `box-wrapup`); move the loose benchmark
  files out of `~`.

- **RAG source governance before any ingest.** `config/rag_sources.txt` declares
  `F:\AI-Brain-Data` and `F:\BIMpossible-Workspace` whole; nothing is ingested yet. Write the
  approved roots, exclusions (client data categorically?), citation rule and re-index/delete
  behaviour before the first index run.
- **Local-model behavioural lane for BIMpossible CI (cross-repo).** A local-provider eval runner
  with its own evidence, never labelled as provider evidence. New consumer of `mybuddy`; needs
  its own scope before building. Details live in the private BIMpossible repo.

## Needs your call

```
The chat-UI pilot (~/mybuddy-pilot: Open WebUI, AnythingLLM, LibreChat) runs permanently on the
box that NORTHSTAR calls "the instrument" and says is "not a desktop". It is not a game or Revit,
and it is localhost-only, so today it breaks no off-limits line. But LibreChat alone adds four
always-on services, and every chat UI can evict the working model. Two readings:

  (a) The pilot is a consumer of the endpoint — exactly what the mission exists to serve. Keep it,
      record pilot state in batch identity, done.
  (b) The pilot is desktop-shaped load on the instrument. Move it to the rig (or a container host)
      and let the box serve only the API.

Pick one so the roadmap items above ("batch identity", "residency policy", "LibreChat endpoint")
know whether they are worth doing. Until then the endpoint work continues unchanged.
```

```
The handoff's Priority 5 proposes an agent harness on the box (Goose + MCP servers + approval
boundaries + audit log). That is a new subsystem, not in the NORTHSTAR mission and not a fix.
Not built. If you want it, it deserves its own NORTHSTAR.<slug>.draft.md — say so and one gets
drafted; until then it stays parked here.
2026-09-21 update: the personal-AI handoff moves Goose to the RIG (disposable worktree, local
endpoint via :11440), which removes the "instrument box" objection. Still a new subsystem —
same draft route.
```

```
Scope split (personal-AI handoff): treat mybuddy as infrastructure and a "Personal AI Workspace"
(cockpit UI, agents, curated RAG, cloud routing, MCP/tool authority) as a separate consumer
project. Consistent with the mission, but it is a new project. Yes -> a
NORTHSTAR.personal-ai.draft.md gets drafted for you to lock; no -> the items stay parked.
```

```
Raw Ollama :11434 is on 0.0.0.0 without auth — accepted at the 09-13 closeout. New fact since:
three chat UIs run on the box, and any LAN/tailnet peer can bypass the :11440 Bearer gateway.
Keep as settled, or reopen (rebind to loopback / UFW to gateway only)? Box unchanged until told.
```
