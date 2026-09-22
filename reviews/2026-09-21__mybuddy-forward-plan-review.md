# MyBuddy forward plan: pre-implementation review (2026-09-21)

**What this reviews:** the owner's `mybuddy-forward-plan-review-prompt.md` and
`plans/2026-09-21__mybuddy-ai-server-plan.md`.

**How it was done:**
- Read the repository records: NORTHSTAR.md, WORKLOG.md, `decisions/`, and `ops/Caddyfile`
  on the box.
- Ran read-only probes over `ssh mybuddy` on 2026-09-21 / 22 UTC. These covered listeners,
  unit files, compose files, env files, the box checkout and the venvs.
- Nothing on the box was changed. No containers were touched and no service was restarted.

**Naming:** "Buddy" means MyBuddy, the local AI system as a whole. AI-Server is its inference
infrastructure. The three chat UIs are a pilot and bakeoff that consume that endpoint.

---

## 1. Executive recommendation

**Sequence.** Everything is in order except the first item: a Git-hygiene blocker that was
found during this review (§10). It has been remediated at the branch tip, but purging it from
history is your call. After that, the order is:

1. **Phase 1.** Keep AI-Server honest: housekeeping, a dedicated project venv, recording pilot
   load in batch identity, scoring the four models, and the status/start/stop scripts.
2. **Confirm G1–G4.** The defaults are below.
3. **Phase 2.** Route the three UIs through `:11440` one at a time. Only after all three are
   proven, restrict `:11434`.
4. **Residency policy.**
5. **UI bakeoff and selection record.**
6. **Phase 3 governance document.** No ingestion.
7. **Launcher.** Designed only for now; it gets built after the bakeoff chooses which UIs
   survive.

**Primary risks.** Each was found by inspection, not assumed.

- **R1: the gateway isn't reachable from containers today.** Caddy `:11440` binds only to
  loopback, the LAN IP and the tailnet IP. The containers reach the host via the Docker bridge
  gateway, which the plan's `host.docker.internal` maps to `172.18.0.1`. Nothing listens there
  on `:11440`. Phase 2 therefore needs a small gateway bind change, or a documented
  container-to-LAN-IP path. The UI settings alone are not enough. This is the one real design
  decision in Phase 2 (§5.1).
- **R2: there's no AI-Server venv on the box.** The only interpreter with `sqlite_vec` is
  `~/.venvs/local-intel`, which belongs to another project. The scheduled-acceptance fix needs
  a dedicated AI-Server venv first. System Python 3.14 has no ensurepip, so this uses the same
  no-pip venv plus sideloaded wheel pattern as Personal-OCR.
- **R3: `OLLAMA_MAX_LOADED_MODELS=2`, together with each UI's own model and `keep_alive`
  settings.** A UI can load a second model next to the pick, and then a benchmark measures a
  contended GPU. Residency and batch identity have to be settled before the models are scored.
- **R4: AnythingLLM keeps its LLM settings inside its container storage, not in a file on
  disk.** Its current configuration can't be inspected without Docker access, which needs sudo
  with a PTY. Plan for one owner-run inspection step.

---

## 2. Verified current state and open assumptions

### Confirmed (live, 2026-09-21)

| Fact | Evidence |
|---|---|
| Listeners are `*:11434` (Ollama); `:11440` on `127.0.0.1`, `<box-lan-ip>` and `<box-tailnet-ip>`; UIs on `127.0.0.1:3000/3001/3080`; `:22` | `ss -ltn` |
| Ollama unit: `OLLAMA_HOST=0.0.0.0:11434`, `KEEP_ALIVE=-1`, `NUM_PARALLEL=1`, `MAX_LOADED_MODELS=2`, `CONTEXT_LENGTH=32768`, models on `/srv/models` | `systemctl cat ollama` |
| The gateway is a **system** unit `aiserver-gateway.service`, which runs `caddy run --config /etc/ai-server/Caddyfile` with `EnvironmentFile=/etc/ai-server/gateway.env`. It refuses to start with a key shorter than 32 characters | `systemctl cat` |
| The Caddyfile bind is `{$GATEWAY_BIND:127.0.0.1}` and the upstream is `{$GATEWAY_UPSTREAM:127.0.0.1:11434}`. The gateway already talks to Ollama over loopback | `~/AI-Server/ops/Caddyfile` |
| `aiserver-preload.service` runs `/usr/bin/python3 /home/zetard/AI-Server/scripts/preload.py` from the **main checkout**, not a worktree | `systemctl cat` |
| `aiserver-endpoint-watch.timer` runs every minute | `list-timers` |
| **No scheduled-acceptance timer exists.** The 09-13 acceptance was a transient `systemd-run --user` | unit listing; `decisions/2026-09-13__scheduled-acceptance-env-gap.md` |
| The box checkout `~/AI-Server` is `main` at `c135da1`, **6 commits behind** `origin/main`, clean | `git rev-list` |
| The merged worktrees `box-mission`, `box-phase0` and `box-wrapup` are still present | `git worktree list` |
| The loose home files are `ai_stress_test.csv` and `ollama-benchmark.py` | `ls ~` |
| Open WebUI: `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `extra_hosts host.docker.internal:172.18.0.1`, port `127.0.0.1:3000:8080` | `open-webui/compose.yaml` |
| AnythingLLM: `compose.yaml` only, with **no `.env`**. The LLM provider is configured in the UI and stored in the container volume | directory listing |
| LibreChat: `app/.env` has `OLLAMA_BASE_URL=http://host.docker.internal:11434`. **No `librechat.yaml`** exists, only `librechat.example.yaml`. The Langfuse fanout lives in an optional override compose file | `grep`, `ls` |
| There is no AI-Server venv. `~/.venvs/local-intel` has `sqlite_vec`; `/usr/bin/python3` and `cuda-build` do not | import probe |
| The user `zetard` isn't in the `docker` group, and `ufw` needs root | `id`, `ufw status` |

### Must be inspected before implementation (owner-run, needs sudo with a PTY)

- `docker network ls` and `docker network inspect` for each pilot's network: the subnets and
  gateways. The WORKLOG claims `app_default = 172.20.0.0/16`, but this session couldn't see it.
- `sudo ufw status numbered`. The WORKLOG says there are two rules covering `.18` and `.19`;
  not verified here.
- AnythingLLM's current provider settings: the UI settings page, or `docker exec … env` plus
  its storage `.env`.
- Whether the LibreChat stack actually running includes the Langfuse override:
  `docker compose ps`. If it does, telemetry leaves the box, and that has to stop.
- Each UI's per-request `keep_alive` and default-model behaviour. Read these from the live
  container settings.
- `/etc/ai-server/gateway.env`, for the `GATEWAY_BIND` value only. Never print the key.

---

## 3. Decision register

| # | Decision | Proposed default | Owner confirmation | Unlocks |
|---|---|---|---|---|
| G1 | Pilot placement | Keep the pilot on MyBuddy as an endpoint consumer for the bakeoff. Don't move it to the rig | **Required** | Phase 2 staying on the box; launcher design |
| G2 | Raw `:11434` | **Reopen** the 09-13 acceptance. Restrict it to loopback, or to loopback plus the documented container path, *only after* all three UIs are proven through `:11440` | **Required.** This reverses a closeout acceptance | Phase 2 step 5 |
| G3 | A separate Personal AI Workspace project | **No, not yet.** Revisit after the cockpit is chosen and RAG governance is approved | **Required** | Nothing now. It keeps Phase 4 parked |
| G4 | Goose | Park it with G3. When it does come, it runs on the rig, under explicit tool boundaries | **Required** | Nothing now |
| G5 *(new, from R1)* | How containers reach `:11440` | (a) **Recommended:** one pinned-subnet Docker network `mybuddy-consumers` shared by the three UIs. Caddy also binds that network's gateway IP, with `After=docker.service`. (b) Containers call `<box-lan-ip>:11440`, with a UFW allow from the consumer subnet. This is fragile if DHCP moves the IP. (c) Caddy binds `0.0.0.0` and UFW limits it. Broader, not recommended | **Required.** It changes a committed gateway config | Phase 2 steps 1–4 |

---

## 4. Phase 1 implementation proposal

| WP | Change | Files / services | Verification | Rollback | Risk if skipped |
|---|---|---|---|---|---|
| 1.1 | Merge PR #21 (records only). Fast-forward `~/AI-Server` to `origin/main`. Prune the 3 merged worktrees. Move `ai_stress_test.csv` and `ollama-benchmark.py` into `~/bench-archive/` | box checkout only | `git status` clean, and `worktree list` shows only main. Then `systemctl restart aiserver-preload` and check the endpoint still returns 200 through `:11440` | `git reset --hard c135da1`; move the files back | Box scripts drift from the repo. "Gateway units on a worktree path" is **already resolved**: the units read `/etc/ai-server` and the main checkout |
| 1.2 | **A dedicated AI-Server venv** at `~/AI-Server/.venv`, created with `python3 -m venv --without-pip`, with the pinned deps sideloaded (the Personal-OCR pattern). Never use `local-intel`'s venv | new `.venv` (gitignored); `scripts/bakeoff-session.sh` and `scripts/automation_acceptance.py` resolve `$ROOT/.venv/bin/python`, otherwise fail with a message; log `sys.executable`; preflight `import sqlite_vec` | Unit tests in `tests/` for the resolver and preflight, using a mock interpreter path. On the box: one `systemd-run --user` acceptance run exits 0 with `sys.executable` logged | Delete `.venv` and revert the script commit | The acceptance harness can't run unattended, which is the WP-F criterion's own evidence path |
| 1.3 | Batch identity records pilot load: `pilot_ui_ports_listening` (HTTP probes of 3000/3001/3080), plus `loaded_models` from the runner's `/api/ps` as best-effort ops enrichment | `eval/` identity writer; test with a stdlib mock | A unit test shows the fields present, and absent with the reason "probe failed" rather than a crash | Revert | A contended GPU gets recorded as a clean measurement |
| 1.4 | Score the four models with `eval/` on the box. Stop the pilot first (the owner runs `docker compose stop` in each), with batch identity recorded. `config/models.txt` changes only if a challenger beats gemma4 on WP-F | `out/` results; a decision record | The decision record includes each model's WP-F score and batch identity | Nothing to revert unless `models.txt` changes; then revert that line | The model pick goes stale without evidence |
| 1.5 | `scripts/mybuddy-status` / `-start` / `-stop`, in plain English. Status: HTTP probes of the runner (loopback over SSH), `:11440/v1/models` with the key, and the three UI ports. Start and stop wrap `docker compose up -d` / `stop` per UI and say plainly when sudo is needed | `scripts/` only; mock-endpoint tests | Every probe degrades to "unknown (reason)", never a traceback. No runner name in any client-facing key | Delete the scripts | The owner keeps having to learn Docker, SSH and ports |

Order: 1.1 → 1.2 → 1.3 → 1.5 → 1.4. Scoring goes last so it uses the new identity fields.

---

## 5. Phase 2 migration proposal

### 5.1 The network path (G5): do this first

Recommended, option (a):
- Create a Docker network `mybuddy-consumers` with a pinned, documented subnet, chosen after
  the inspection so it doesn't collide with an existing one.
- Attach each UI's service to it as an external network.
- Add that network's gateway IP to `GATEWAY_BIND`. It's multi-address, like today's.
- Add `After=docker.service` and `Wants=docker.service` to `aiserver-gateway`, so the bridge
  IP exists before Caddy binds.
- The committed `ops/Caddyfile` default stays loopback, and the box value lives in
  `/etc/ai-server/gateway.env`.
- Add a UFW rule: allow from the consumer subnet to `:11440` only.

### 5.2 UI by UI

Do one UI at a time. The existing Ollama path stays until the new path is proven.

| UI | Mechanism | Endpoint format | Proof from inside the container |
|---|---|---|---|
| **Open WebUI** | Env vars `OPENAI_API_BASE_URL` and `OPENAI_API_KEY`, set from a root-owned env file and **not** committed. Then set `ENABLE_OLLAMA_API=false` once it's proven | `http://<consumer-gw>:11440/v1` | `curl -H "Authorization: Bearer …" …/v1/models` from the container; then one chat in the UI, streaming; the model list shows the pick |
| **AnythingLLM** | UI settings: LLM Provider "Generic OpenAI" (or "OpenAI Compatible"), with the base URL, key, model and context window. Stored in its volume. Embeddings stay off (no RAG, per Phase 3) | `http://<consumer-gw>:11440/v1` | The same curl, then one workspace chat, streaming |
| **LibreChat** | A new `librechat.yaml` with one `custom` endpoint (`baseURL`, `apiKey: ${INFERENCE_API_KEY}` from `.env`, `models.fetch: true`), mounted through a compose override. The example's cloud endpoints are **not** copied | `http://<consumer-gw>:11440/v1` | The same curl, model fetch in the UI, one streamed chat. Confirm the Langfuse override isn't running |

**Order:** Open WebUI (simplest) → LibreChat → AnythingLLM (it needs the UI-stored setting).

**Rollback for each UI:** restore the previous compose, env or UI setting (the old Ollama URL
is still reachable until step 5.3) and restart that one stack.

### 5.3 Restricting raw `:11434` (G2): only after all three pass 5.2

1. Set `OLLAMA_HOST=127.0.0.1:11434` through a systemd drop-in, not an edit to the unit. The
   gateway upstream is already `127.0.0.1:11434`.
2. Restart Ollama. Then re-run the AI-Server acceptance path through `:11440`: the WP-F
   workload plus one unattended automation. Check `/v1/models` from the rig over the tailnet.
3. Remove the old UFW `:11434` container rules. Record the change in `decisions/`.

**Rollback:** delete the drop-in and restart. The previous state comes back in one step.

---

## 6. Model residency proposal

The problem: `OLLAMA_KEEP_ALIVE=-1` is only the server default. A UI's per-request
`keep_alive`, or a different model choice, overrides it. With `MAX_LOADED_MODELS=2`, a UI can
also load a second model beside the pick.

| Option | Mechanism | How it's verified |
|---|---|---|
| A. The gateway normalizes it | Caddy strips or overwrites `keep_alive` on `/v1/*`. This only works if the OpenAI-compatible path forwards it at all, which has to be tested | Send `keep_alive: 0` through `:11440`, then check `/api/ps` still shows the pick resident |
| B. The UIs are pinned | Each UI is configured with only the pick as its model and no keep-alive override. The gateway restricts `model` to an allow-list | The UI model lists show only the pick; `/api/ps` after a session |
| C. Re-warm on a timer | `preload.py` becomes a timer that re-warms the pick every N minutes | `/api/ps` history; cold-load counts in the digest |
| D. `MAX_LOADED_MODELS=1` | The runner holds one model, so a UI's other model evicts the pick. Visible, but worse | — |

**Recommended: B, with C as a safety net.** Add A if the test shows `keep_alive` passes
through the OpenAI path.

**Acceptance check:** after a scripted 30-minute session per UI, `/api/ps` shows only the pick
resident, and no cold load over 10 s appears in the endpoint-watch log.

---

## 7. UI bakeoff design

**Precondition:** all three UIs pass 5.2, and residency passes §6. Every run uses the same
model (the pick), temperature 0.2 and a 32k context.

**Tasks (10), run in each UI:**
1. Quick question and answer.
2. A multi-turn follow-up.
3. A 20k-token paste followed by a summary.
4. Code explanation.
5. Structured JSON output.
6. Stop mid-stream and resume.
7. Box-offline behaviour: stop the gateway for 30 s.
8. Search and retrieve the conversation history.
9. Model discovery after a new model is added.
10. Export a conversation.

**Rubric:** each item is scored 0–3, and each score needs one evidence field (a screenshot
path, a log line, or a measured time).

| Axis | Weight | What is measured |
|---|---|---|
| Daily UX, "feels like MyBuddy" | 25 | Time to first token as perceived, clicks per task, owner rating after one week of use |
| AI-Server compatibility | 20 | Discovery, streaming, reconnect, error clarity, metadata (tokens, model) |
| Retrieval and citations (future) | 10 | Whether it *can* show provenance. Not exercised, since there's no ingestion |
| Tools/MCP control | 10 | Whether tools can be off by default, and whether AI-Server stays the only model authority |
| Architecture overlap | 10 | Its own databases, RAG or agent stacks, hidden state |
| Operations | 15 | Upgrade path, backup scope, idle RAM and VRAM, dependencies, recovery |
| Security | 10 | Secrets handling, consumer-only posture, least privilege, outbound traffic |

**Decision rule:** the highest weighted score wins, **unless** it scores 0 on Security or on
AI-Server compatibility, which disqualifies it. Ties go to the lower operations burden.

**Record:** `decisions/<date>__cockpit-ui-selection.md`, containing the scores, evidence
links, the winner, and the fate of each other UI: kept for a narrow named purpose, paused
(`compose stop`), or removed **only with explicit approval**. Volumes are kept until you say
otherwise.

**Burden:** about 2 hours per UI for the tasks, plus one week of daily use of the leading
candidate.

---

## 8. Phase 3 RAG-governance proposal (outline only)

**No indexing or ingestion happens in Phase 3 or in this review.**

Outline of `docs/rag-source-governance.md`:
1. Purpose and scope: which consumer may query which index.
2. Approved source roots. Replace today's whole-root entries (`F:\AI-Brain-Data` and
   `F:\BIMpossible-Workspace`) with explicit subfolders.
3. Exclusions and sensitive classes: client data, credentials, personal documents, and
   anything under an NDA.
4. The standing rule: no client data on MyBuddy until an explicit, separate approval (the
   NORTHSTAR OCR hard stop).
5. Copies created and where they live: chunks, embeddings, the vector index and the UI's own
   RAG databases. Each one is named with its drive and retention.
6. Citation and provenance: the source path, the modified time, and a hash on every answer.
7. Re-index and deletion: a source deletion propagates within N days, with a verifiable purge.
8. Approval: the owner signs the root list. Only after that is `config/rag_sources.txt`
   narrowed, in a single reviewed commit.

---

## 9. One-click access design (concept only, not implemented)

- **Form:** a Windows shortcut that runs `mybuddy-open.ps1 [owui|anything|libre|all]`.
- **Behaviour:**
  1. Test `ssh -o BatchMode=yes mybuddy true`, with a 5 s timeout. On failure it shows
     "MyBuddy is offline or asleep" and exits.
  2. Look for a live forward: check the listener on local `13000/13001/13080`, owned by
     `ssh.exe`. It reuses a forward if one exists.
  3. Otherwise start `ssh -N -L 13000:127.0.0.1:3000 …` hidden, as a background job. There is
     no terminal window.
  4. Open the browser at the chosen `http://127.0.0.1:1300x`.
  5. `mybuddy-open.ps1 -Stop` closes the forwards.
- **Keys:** the existing `ssh mybuddy` key only. No passwords are stored.
- **When:** built after §7, and only for the UIs that survive.

---

## 10. Security and data-boundary review

- **Public-repo exposure (found during this review, and a blocker). AI-Server is PUBLIC.**
  Earlier commits on PR #21 in this session (`094c9bd`, `faceacc`) pushed two things:
  - BIMpossible PR #671 security-planning detail: tenant-isolation files and WFA finding IDs,
    for a **private** repo;
  - the box's LAN and tailnet IPs, which earlier merged records also contain.

  **Done at the branch tip:**
  - The #671 plan and decision were moved to the private BIMpossible repo, as a local commit
    `f20ede84` on the unpushed branch `docs/pr671-resolution-plan`.
  - They were removed from AI-Server.
  - The IPs were replaced with `<box-lan-ip>` and `<box-tailnet-ip>` in every tracked file.

  **Still exposed:** the Git history of PR #21's branch, and the merged `main` history for the
  IPs. Purging needs a force-push or a history rewrite, which is your call (§12 Q1).
- **Secrets:**
  - `INFERENCE_API_KEY` lives in `/etc/ai-server/gateway.env`, root-owned.
  - Keys for the UIs go into root-owned env files beside each compose file, and never into Git
    or the example yaml.
  - No cloud provider keys anywhere in the pilot tree.
- **Network:**
  - The target is `:11440` as the only door.
  - `:11434` goes to loopback after G2.
  - UIs stay on `127.0.0.1` and are reached only through SSH forwards.
  - Never port-forward.
- **Outbound traffic:** confirm there is no Langfuse or telemetry override in LibreChat, and
  disable telemetry in each UI's settings.
- **Data roots:**
  - No work files on `/srv/models`.
  - UI volumes stay in Docker's default root.
  - Automations never write into `AI-Brain-Data` or `BIMpossible_Workspace`.
- **Agent authority:** none granted in any phase here. UI tools and MCP stay off by default.
- **Rollback:** every Phase 2 step keeps the previous path working until the next one is
  proven. `:11434` changes only through a drop-in.

---

## 11. Implementation backlog

| # | Work package | Owner approval before execution? |
|---|---|---|
| 1 | Merge PR #21, after deciding the history question (Q1) | **Yes** (merge + Q1) |
| 2 | WP 1.1: box checkout fast-forward, worktree prune, file archive | No |
| 3 | WP 1.2: AI-Server venv, interpreter resolver, preflight, tests, one acceptance run | No |
| 4 | WP 1.3: batch identity pilot-load fields and tests | No |
| 5 | WP 1.5: `mybuddy-status` / `-start` / `-stop` and tests | No |
| 6 | WP 1.4: score four models, with the pilot stopped | No. The owner runs `compose stop` (sudo) |
| 7 | Owner inspection: Docker networks, UFW, AnythingLLM settings, Langfuse check | Owner-run (sudo) |
| 8 | G5 network plus gateway bind, and the UFW rule | **Yes** (G5) |
| 9 | Open WebUI → LibreChat → AnythingLLM through `:11440`, each proven | **Yes** (G1) |
| 10 | Residency policy B+C, and its acceptance check | No, once G1 is confirmed |
| 11 | `:11434` to loopback, then re-run acceptance | **Yes** (G2) |
| 12 | UI bakeoff and selection record | Owner does the scoring |
| 13 | RAG governance document draft | Draft no; approval yes |
| 14 | Launcher | **Yes**, after 12 |

Items 2–6 are in the mission and pre-approved by the NORTHSTAR. They can start right after
this review.

---

## 12. Questions requiring an owner answer

1. **Public-history purge.** Should PR #21's branch history be rewritten, with a force-push,
   to drop the #671 detail and the IPs before it merges? Should the IPs in already-merged
   `main` be accepted, or purged too? Recommended: rewrite the PR branch, and accept `main`
   (private-range and tailnet IPs, low value to an outsider).
2. **G1–G5.** Confirm the defaults in §3, especially G2 (reverses a closeout acceptance) and
   G5 option (a) (changes the committed gateway bind story).
3. **The #671 docs.** Push the private BIMpossible branch `docs/pr671-resolution-plan`, which
   is local only right now?
