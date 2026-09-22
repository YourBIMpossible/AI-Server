# Review — MyBuddy strategy reconciliation & phased implementation (final round)

**Date:** 2026-09-22 · **Reviewed:** `mybuddy-strategy-reconciliation-and-phased-implementation.md`
(owner's Downloads copy, not in this repo) · **Mode:** read-only review. No box or repo changes.

**Evidence labels, for the reviewer.** Only the reviewing Claude session had some of this
knowledge, so each comment says where its evidence came from:
- **[repo: path]** — a file in this repo (`YourBIMpossible/AI-Server`) at `origin/main`.
- **[local-intel: path]** — a file in the separate `F:\Local Intel` repo (last commit
  `1d3ce46`, 2026-09-06).
- **[box]** — observed live on the box (`mybuddy`) in this session.
- **[session]** — something done or learned in the 2026-09-21/22 sessions that no committed doc
  records yet.
- **[unverified]** — not checked.

## Verdict

**Approve, with one blocker for P1 and five corrections.** The plan already adopts the PR #26
comments: the mission split, rig-only cloud calls, P8 rejected, a baseline first, backups, and the
27/27 caveat. Its structure (eras, P0–P8, authority classes A0–A4) is sound. The blocker is that
P1 assumes local-intel can use the box endpoint through the gateway, and today it cannot.

## Blocker

### B1 — local-intel cannot reach the gateway as written (P1 Gate A)

- **[local-intel: `local_intel/ollama_client.py`]** The client has
  `DEFAULT_HOST = "http://localhost:11434"`. It calls the runner-native `/api/generate`, sends no
  auth header, and makes no `/v1/*` calls.
- **[repo: `ops/Caddyfile`]** The gateway (`:11440`) proxies only `/v1/*`, and only with a Bearer
  `INFERENCE_API_KEY`. Runner-native `/api/*` requests get a 404.
- **Why the obvious fix is not free.** Porting the client to `/v1/chat/completions` changes the
  frozen §9 request parameters. Ollama's OpenAI-compatible API does not accept `num_ctx` per request,
  so context length would have to come from the server default (`OLLAMA_CONTEXT_LENGTH` = 32768 on
  the box). Under local-intel's rules that is a versioned protocol change, not a refactor.

**Ask:** Gate A should name one of three routes explicitly:
1. **Port the client to `/v1`.** This is a versioned local-intel protocol edit, with `num_ctx`
   handled by the server config.
2. **Document a raw-`:11434` exception for local-intel from the rig.** `:11434` is already accepted
   for the private setup [repo: `WORKLOG.md` → *Needs your call*, which points to
   `plans/2026-09-21__mybuddy-ai-server-plan.md`]. This is the cheapest route.
3. **Let the gateway pass `/api/generate`.** Not recommended, because it breaks the project
   contract of no runner-native paths for clients [repo: `CLAUDE.md` → *The contract*].

## Corrections

### C1 — P1 runs under local-intel's own phase gates

- **[local-intel: `NORTHSTAR` (draft)]** It forbids skipping or reordering phases and requires a
  human-approved, versioned decision for every state change.
- **[local-intel: `decisions/2026-09-06-defer-revision-warm-session-only.md`]** This is the current
  state:
  - Local models are approved for warm-session use only.
  - `qwen3-coder:30b-a3b-q4_K_M` is *eligible* for a future Phase 1a admission.
  - `qwen2.5-coder:14b` is not admitted, and the 9B is unresolved.
  - **No Phase 1a admission has been made.**
- **[local-intel]** Its Phase 0 was measured on the rig (`workstation-zeria-01`). Under its
  hardware-identity rule, those numbers do not carry over to the box.

**Ask:** Rename P1 to "local-intel Phase 0 re-run on the box, then the Phase 1a admission
decision". The first real step is a human admission decision, not a build.

### C2 — The model the plan assumes is not the protocol's model

- The box pick is `gemma4:26b-a4b-it-q4_K_M` [repo: `config/models.txt`,
  `decisions/2026-09-13__runner-and-model-pick.md`]. **gemma4 is not a local-intel protocol
  candidate.** Its candidates are the Qwen coders (see C1).
- **[box]** Ollama runs with NUM_PARALLEL=1 and MAX_LOADED_MODELS=2, so there is a single queue.
  Loading a protocol model alongside gemma4 either competes for VRAM with the three chat UIs or
  evicts gemma4. That already happened once after scoring [repo: `WORKLOG.md` → Roadmap
  *Residency after scoring*].

**Ask:**
- Say that P1 measurements need a run window with the UIs stopped. The 2026-09-21 scoring used
  this method [repo: `decisions/2026-09-21__model-scoring-qwen3.5-9b.md`].
- Say that gemma4 residency is restored afterwards.

### C3 — Keep-alive policies conflict

- **[box]** The box runs `OLLAMA_KEEP_ALIVE=-1`, and the three UIs are pinned to keep-alive forever
  [repo: `WORKLOG.md` Done, 2026-09-21].
- **[local-intel]** The local-intel protocol uses a 30-minute keep-alive.
- A keep-alive sent with a request overrides the server default. A benchmark has already left the
  box model cold this way [repo: `decisions/2026-09-16__box-state-and-chat-uis.md`].

**Ask:** P1 should state whose keep-alive wins during and after a run.

### C4 — "Era 1 substantially complete": cite the evidence and name what is still open

**Evidence to cite:**
- [repo: `decisions/2026-09-13__northstar-closeout-check.md`] — all five criteria are Met.
- [repo: `decisions/2026-09-13__box-phase0-remeasure.md`]
- [repo: `decisions/2026-09-13__wp-h-runner-bakeoff.md`]
- [repo: `decisions/2026-09-13__runner-and-model-pick.md`]

**What is still open:**
- **Criterion 3 carries a caveat.** The unattended `daily-digest` run cleared WP-F on the bakeoff's
  qwen3moe artifact, *not on gemma4*. It also ran from a transient timer, and no schedule is
  installed.
- **Scheduled acceptance fails under `systemd-run --user`**, because the system Python lacks
  sqlite-vec. This is an environment gap, not a regression
  [repo: `decisions/2026-09-13__scheduled-acceptance-env-gap.md`].
- **The box `.env` has no `WORKSPACE`.** It falls back to a Windows path, so a digest job on the box
  would fail [repo: closeout check → Flags].

**Ask:** Era 1 is complete for the endpoint and incomplete for unattended automation on the chosen
model. P0 or P2 should include "one installed-schedule job on gemma4 clears WP-F".

### C5 — The backup exists, but a restore has not been tested

- **[session, box]** A one-off backup exists: `~/mybuddy-ui-backup-20260922.tgz` (874 MB). It is a
  tar of `/srv/data/mybuddy/`, taken with all three UIs stopped, during the 0.11.4 update and the
  path rename.
- There is no schedule, no off-box copy, and no restore test.

**Ask:** The plan's backup item should be "scheduled, copied off the box, and restore-tested once".
Taking a backup is already done.

## Minor / informational

- **Paths changed on 2026-09-22 [session, box; repo: PR #27].**
  - UI configs now live in `~/mybuddy/{open-webui,anythingllm,librechat/app}`, and UI data in
    `/srv/data/mybuddy/`.
  - The `mybuddy-pilot` paths are gone.
  - Open WebUI is now 0.11.4 and still tracks `:main`.
  - Any path in the plan should use the new names.
- **LibreChat's UFW rule depends on the `app_default` bridge [repo: `WORKLOG.md` Done 2026-09-21].**
  If P-phases recreate that compose network, the rule has to be added again. List this as a P2/P4
  risk.
- **P3 RAG.** Point it at the existing Roadmap item *RAG source governance before any ingest*
  [repo: `WORKLOG.md`]. `config/rag_sources.txt` still declares whole folders, and nothing has been
  ingested.
- **§9 authority model and OpenCode.**
  - PR #25 reviews OpenCode, whose config currently points at the rig's dead Ollama [session].
  - An agent-capable client is where A2–A4 authority becomes real.
  - Classify OpenCode explicitly before it is pointed at the box.
- **[unverified]** The plan names `evidence-compiler` and `claude-profile` integration paths. This
  review did not check them.
- **Lineage.** The plan builds on PR #26 (`reviews/2026-09-21__mybuddy-strategy-review.md`). PRs #25,
  #26 and #27 are all still unmerged, so the plan cites documents that are not yet on `main`. Merge
  them first, or cite them by PR.

## Recommended order before "moving forward"

1. Merge PRs #25, #26 and #27.
2. Decide the B1 route. Option 2 is the cheapest.
3. Make the human local-intel admission call (C1).
4. Book a run window: UIs stopped, and gemma4 re-warmed afterwards (C2, C3).
