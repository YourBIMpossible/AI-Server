<!-- Imported verbatim from the owner's Downloads on 2026-09-21 (written by a separate chat session, not this repo). Routing and the PR #671 call: decisions/2026-09-21__personal-ai-and-pr671-ci-plan.md -->

# MyBuddy / AI-Server — Session Handoff

## Executive position

We have a working dedicated local inference box, `mybuddy`. It is a headless Linux inference appliance, not a desktop and not yet a complete personal-AI system.

The immediate problem identified is that the box currently has no satisfying human interaction layer: no browser chat UI, no agent harness, no personal workspace, and no controlled tool bridge to a development machine. It can be reached through SSH and an OpenAI-compatible API, but that is infrastructure—not the user experience I want.

The recommended direction is a staged hybrid personal-AI environment:

1. Preserve `mybuddy` as a private local inference appliance.
2. Add a browser-based AI workspace/cockpit, likely Open WebUI first, as a reversible learning tool—not as the permanent product.
3. Add a local terminal agent/harness, likely Goose, on the development rig—not necessarily on `mybuddy`—for scoped local-model coding experiments.
4. Continue using a frontier/cloud coding agent for consequential engineering work until local models demonstrate equivalent or better outcomes on evidence-backed benchmarks.
5. Add retrieval, MCP/tools, workflow automation, and eventually a custom UI only after basic chat and agent loops are proven valuable.
6. Keep model serving replaceable behind the existing OpenAI-compatible API boundary. Ollama is current. vLLM is deferred pending a measured reason.

The important mindset: do not build a giant autonomous “AI platform” first. Build a useful daily interaction loop, evaluate it with real work, then add narrowly scoped capabilities.

---

# Confirmed current state

## Machine identity and access

- Hostname: `mybuddy`
- Login user: `zetard`
- LAN IP: `192.168.1.128`
- Tailscale IP: `100.89.51.34`
- Tailscale MagicDNS: `mybuddy`
- SSH: passwordless from the rig via `ssh mybuddy`
- OS: Ubuntu 26.04.1 LTS
- Hardware:
  - Intel i9-14900KF
  - 61 GiB RAM
  - NVIDIA RTX 3090, 24 GiB VRAM
  - NVIDIA driver 595.91.07 / CUDA 13.2
- Storage:
  - `/srv/models`: dedicated model store
  - `/srv/data`: reserved data/services drive, currently near-empty
  - `/home/zetard`: project checkouts and box-local work

## Current serving architecture

The intended client path is:

```text
client
  -> authenticated Caddy gateway on `mybuddy:11440/v1`
  -> Ollama on `:11434`
  -> local GPU models
```

The canonical UI/client contract is:

```text
INFERENCE_BASE_URL = http://mybuddy:11440/v1
INFERENCE_API_KEY  = <from /etc/ai-server/gateway.env>
INFERENCE_MODEL    = dynamically selected/listed model
```

Key details:

- `aiserver-gateway.service` is Caddy.
- Gateway exposes only portable OpenAI-compatible `/v1/*`.
- Gateway requires `Authorization: Bearer <INFERENCE_API_KEY>`.
- Gateway binds only loopback, LAN, and Tailscale—not public Internet.
- Gateway supports token streaming and long requests.
- Clients should use `/v1/models` dynamically rather than hardcoding a model tag.
- The runner implementation is deliberately hidden from clients behind the OpenAI-compatible contract.

## Raw Ollama state

- `ollama.service` is active and enabled.
- Ollama version observed: 0.34.0.
- Raw runner listens on `0.0.0.0:11434`.
- Raw runner is currently unauthenticated.
- Configuration includes:
  - `OLLAMA_CONTEXT_LENGTH=32768`
  - `OLLAMA_FLASH_ATTENTION=1`
  - `OLLAMA_KEEP_ALIVE=-1`
  - `OLLAMA_NUM_PARALLEL=1`
  - `OLLAMA_MAX_LOADED_MODELS=2`

Important: `:11434` is an operational/raw runner port, not the port a UI or agent should use. Because it is currently LAN/tailnet reachable without auth, direct use bypasses the intended gateway authorization boundary. Longer term, decide whether to firewall/rebind it to loopback and make `:11440` the only reachable serving door.

## Current model bench

Current pulled models include:

- `nemotron-3.5-lightning:30b-a3b-q4_K_M` — general reasoning candidate
- `qwen3-coder:30b-a3b-q4_K_M` — coding candidate
- `qwen3.8:27b-q4_K_M`
- `gemma4:31b-it-q4_K_M`
- `gemma4:26b-a4b-it-q4_K_M` — personal OCR production candidate
- `qwen3.5:9b` — fast/smaller utility candidate
- `qwen2.5-coder:14b` — has a known plain-text tool-call caveat
- `nomic-embed-text:latest` — embeddings

This is a working bench, not a final model selection. Model selection is intended to be a configuration choice backed by evaluation data, not a hardcoded UI choice.

## Important host/runtime constraint

System Python on the box is Python 3.14.4 and lacks normal `pip`, `ensurepip`, and `venv` support. Do not casually add a Python app/runtime to the box or alter system Python.

The practical implication: prefer services/clients that interact over HTTP with `mybuddy:11440/v1`, use containers where appropriate, and avoid introducing a Python-heavy UI backend directly on the box unless there is a specific, validated deployment plan.

---

# Existing project north star

There is a `NORTHSTAR.draft.md`; it is explicitly a draft and has not been locked/renamed to `NORTHSTAR.md`.

Its core framing is:

> Stand up and maintain one dedicated, headless, always-on local inference endpoint that internal tooling can rely on, and make local-model performance measurable so model decisions are evidence-based.

The box is characterized as an instrument for stable local-model evaluation, not simply “more VRAM for bigger models.”

The draft’s current explicit constraints:

- No public exposure; LAN/Tailscale only.
- No customer/client data on this box until the separate OCR/security hard-stop is resolved.
- No vLLM unless single-user is no longer true; current draft says Ampere does not justify it.
- No reuse of previous 5080 rig measurements; remeasure on this dedicated box.
- Not a desktop; do not run Revit or games on it.

Explicit out-of-scope items in the draft:

- Customer-facing local inference.
- Larger embedding models without a concrete consumer.
- Rescuing the GPU OCR service before its separate security review.

The project also has a RAG config file with currently declared read-only source roots:

```text
F:\AI-Brain-Data
F:\BIMpossible-Workspace
```

This indicates retrieval/indexing is contemplated, but it does not mean broad indexing or durable personal memory has been decided or safely implemented.

---

# What was accomplished in this conversation

## 1. Clarified the missing layer

The box already has a working inference layer. It does not have the interaction layer expected from products like Claude Code, Claude/ChatGPT/Perplexity chat, or a true personal assistant.

The missing user-facing components are:

- A browser chat/application UI.
- Conversation/history management.
- Model selection and routing.
- File/document interaction.
- A coding-agent harness.
- Controlled tools for shell/files/Git/GitHub/browser/Revit.
- Deliberate personal/project knowledge retrieval.
- Auditability, evidence, and permission boundaries.

This avoids conflating “a model server exists” with “I have a personal AI.”

## 2. Identified the architecture boundary already in place

The existing authenticated OpenAI-compatible gateway at `:11440/v1` is the correct stable client boundary.

This means chat UIs, coding agents, custom front ends, SDKs, and future serving engines should all target the same contract rather than binding directly to Ollama.

The design supports replacing or trialing serving engines later without rewriting every client:

```text
UI / coding harness / custom app
  -> stable authenticated OpenAI-compatible gateway
  -> current runner: Ollama
  -> optional future runner: vLLM or another compatible engine
```

## 3. Reframed local vs cloud as routing, not ideology

The recommendation is explicitly not local-only and not cloud-only.

Local models are appropriate for:

- Private/general daily chat.
- Document triage and extraction.
- OCR-adjacent workloads.
- Embeddings and retrieval.
- Repo archaeology and low-stakes coding tasks.
- Offline/private capability.
- Controlled local automation once tools are proven.

Frontier cloud models/agents remain appropriate for:

- High-stakes coding changes.
- Complex multi-repo work.
- Difficult debugging.
- Architecture synthesis.
- Refactors where tool-use reliability and self-correction dominate.
- Work where reduced rework is worth more than saved tokens.

The position is: do not prematurely replace a productive frontier coding workflow with local models. Benchmark local agents on representative tasks and promote them only where results earn it.

## 4. Proposed the initial interaction stack

The proposed initial stack is:

- **Open WebUI**: browser-based personal AI cockpit/learning environment.
- **Goose**: local terminal agent experiment/harness, likely run on the development rig.
- **Existing mybuddy gateway**: local OpenAI-compatible inference backend.
- **Existing cloud/frontier coding workflow**: retained as the production coding path until benchmarks justify alternatives.

Open WebUI is proposed as a fast, reversible way to learn what daily personal-AI capabilities are actually valuable: chat, model switching, chats/history, documents, controlled tools, and eventually MCP.

It is not recommended as an unquestioned final product architecture.

Goose is proposed as the way to test local coding models in the actual terminal/repository workflow. It should initially run only in bounded/disposable worktrees with limited tool permissions.

## 5. Identified MCP/tools as a separate controlled capability

MCP should not be enabled broadly on day one.

Recommended tool rollout order:

1. Selected workspace filesystem read.
2. Git read/status/diff/log.
3. Allowlisted build/test commands.
4. GitHub read/search/checks.
5. Explicitly confirmed GitHub writes.
6. Browser research in an isolated profile.
7. Revit read-only metadata/model inspection.
8. Explicitly confirmed Revit writes/automation.

This keeps “talking to the AI” separate from “the AI can act on my machine.”

## 6. Pushed back on premature vLLM adoption

vLLM is not rejected permanently. It is deferred.

The current local problem is interaction quality and agent workflow, not inference throughput. Ollama already exposes the compatible API needed by UIs and agents.

vLLM becomes worth a trial only if a measured need exists, for example:

- Multiple simultaneous users/agents.
- Real throughput/concurrency bottlenecks.
- A desired model that is unavailable or materially worse in the current runtime.
- Need for vLLM-specific serving behavior/API/features.
- A benchmark showing meaningful wins on latency, context behavior, reliability, or throughput.
- Additional GPU capacity / a genuine multi-user workload.

If trialed, keep it behind the same gateway/API boundary.

---

# Current recommended direction

## Principle

Build a practical personal-AI environment through small, evidence-driven vertical slices rather than a large speculative platform.

The first goal is not “autonomous AI.” It is:

> I can open a private browser UI or terminal, use local and cloud intelligence intentionally, obtain useful answers with evidence, and allow controlled tool use only where it adds real value.

## Phase 1 — Private conversational cockpit

Deploy a browser UI, likely Open WebUI, privately on LAN/Tailscale.

Requirements:

- Use the authenticated `mybuddy:11440/v1` endpoint only.
- Do not expose the UI publicly.
- Persist UI data intentionally and back it up.
- Use dynamic model discovery, not hardcoded model tags.
- Present friendly model/use-case labels instead of raw model tags:
  - Local General
  - Local Code
  - Local Fast
  - Frontier Code
  - Frontier Reasoning
  - Optional Auto router later
- Start with limited/no powerful tools enabled.
- Establish one or more versioned system prompts for:
  - General engineering assistant.
  - Product/strategy critic.
  - Document/OCR reviewer.
  - Code/repository assistant.

Primary success criterion:

> The user actually prefers opening this over an SSH terminal for ordinary discussion, local documents, and model experimentation.

## Phase 2 — Local coding-agent evaluation

Run Goose or another suitable local harness on the development rig, not necessarily on `mybuddy`.

Why the rig:

- Repositories, worktrees, Git credentials, IDEs, Docker, Windows tooling, Revit, and build environments live there.
- The inference box should remain a stable, dedicated server instead of becoming a general workstation.

Initial constraints:

- One selected repository/worktree at a time.
- Disposable worktrees for edits.
- Read-only/default-safe permissions first.
- No broad home-directory access.
- No automatic push/deploy.
- No uncontrolled browser/credential access.

Evaluation approach:

- Choose 10 representative real tasks from current BIMpossible work.
- Run comparable tasks through a local-model agent and the existing frontier coding workflow.
- Record:
  - First-pass build/test success.
  - Tool-call correctness.
  - Number of interventions.
  - Diff quality.
  - Regression rate.
  - Wall-clock time.
  - Review time.
  - Local resource cost and cloud spend.
- Route work by results, not ideology.

## Phase 3 — Curated evidence retrieval

Do not call this “memory” yet.

Create a small explicit source corpus first:

- ADRs/decisions.
- Product plans.
- Technical specifications.
- Selected README files.
- Operational runbooks.
- Project planning docs.
- Test evidence and key PR summaries.

Requirements:

- Sources remain canonical, versioned files outside the chat UI.
- Retrieval answers include citations to source files/sections.
- Index only explicitly approved roots.
- Support deletion/re-indexing and visible source scope.
- Do not index home directories, all repositories, email, browser history, or customer data by default.

The existing `rag_sources.txt` roots are a possible starting point, but must be reviewed before ingestion because they are broad Windows roots.

## Phase 4 — One controlled tool at a time

Add tools only when there is a real user story and a visible permission/audit model.

Candidate vertical capabilities:

- “What changed while I was away?” -> Git/GitHub read-only status and summary.
- “Explain this decision.” -> cited retrieval over curated project docs.
- “Run project validation.” -> allowlisted tests/builds in selected worktree.
- “Inspect this Revit model.” -> read-only Revit bridge.
- “Process this document.” -> existing personal OCR pipeline plus a review UI.
- “Is MyBuddy healthy?” -> endpoint/model/service status screen.

Do not start with broad unrestricted shell, arbitrary MCP servers, full desktop control, browser automation with logged-in sessions, or Revit write automation.

---

# Decisions still needed

## Decision 1 — Confirm or revise the project mission

The existing north star defines the box as a measurable internal inference appliance, not a general personal AI.

Need an explicit decision:

- Is the personal-AI interaction layer now part of the same project mission?
- Or is it a separate project that consumes `mybuddy` as infrastructure?
- Does the current NORTHSTAR draft remain accurate?
- Should `NORTHSTAR.draft.md` be edited and promoted to `NORTHSTAR.md`?

Recommended answer:

Treat `mybuddy`/AI-Server as stable infrastructure, and create a separate but adjacent “Personal AI Workspace” project that consumes it. This protects the box’s original measurable-inference purpose from UI/agent scope creep.

## Decision 2 — Browser cockpit choice

Need to choose:

- Open WebUI now as the experiment/learning cockpit.
- LibreChat instead, if multi-provider/agent/workspace features are immediately more important.
- A minimal custom front end now.
- No browser UI; terminal-first only.

Recommended answer:

Use Open WebUI first, privately and reversibly. Do not build a custom UI until 30–60 days of real use reveals the stable product requirements. Do not let Open WebUI become the location of canonical product knowledge, policies, or tool definitions.

## Decision 3 — Cloud model/provider policy

Need to decide how frontier/cloud models fit:

- Local-only.
- Cloud-only for hard tasks.
- Hybrid with user-selected models.
- Hybrid with an automatic router.
- Which providers/accounts can be connected to the UI, if any.

Recommended answer:

Hybrid, initially user-selected rather than auto-routed. Expose clear choices such as Local, Frontier, and later Auto. Do not attach cloud provider credentials to the UI until data handling, billing, retention, and scope are explicitly understood.

## Decision 4 — Coding-agent policy

Need to decide:

- Whether Goose is the first local agent harness to evaluate.
- Whether Claude Code/current frontier harness stays the primary production coding agent.
- Which repositories/tasks can be used for local-agent benchmarks.
- What tool permissions local agents receive.

Recommended answer:

Keep the existing frontier coding agent as production-default. Install/evaluate Goose on the rig using local models and disposable worktrees. Promote it task-class by task-class only after measured results.

## Decision 5 — Raw Ollama port security

Current issue:

- Raw Ollama `:11434` binds `0.0.0.0` and is unauthenticated.
- The intended gateway at `:11440` has Bearer auth.
- LAN/tailnet peers can currently bypass the gateway by calling raw Ollama directly.

Need a deliberate owner decision:

- Keep it temporarily for operations/debugging.
- Restrict with a firewall to local machine/gateway only.
- Rebind Ollama to loopback and let Caddy be the sole external door.
- Establish a separate ops-only authenticated path.

Recommended answer:

Treat `:11434` as a security/configuration cleanup task before expanding user-facing access. The desired end state is raw runner reachable only locally or only by the gateway, with `:11440` as the sole client-facing API.

## Decision 6 — UI hosting and storage model

Need to decide where the browser UI runs:

- On `mybuddy` in Docker/Compose.
- On another always-on private host.
- On the rig.
- In a separate VM/container host.

Also decide:

- Persistent storage location.
- Backup/restore approach.
- LAN/Tailscale-only reachability.
- Single-user versus future multi-user authentication.
- How secrets are mounted/provisioned.

Recommended answer:

Run the initial UI as a private containerized service with explicit persistent volumes and backup. Avoid a custom Python runtime directly on `mybuddy` due to the system-Python constraint. Keep the UI private to Tailscale/LAN and do not public-port-forward it.

## Decision 7 — RAG/source boundary

Need to decide:

- Whether curated project retrieval is an immediate next phase.
- What source roots are approved.
- Whether `F:\AI-Brain-Data` and `F:\BIMpossible-Workspace` are too broad.
- Canonical source locations and required citation behavior.
- Whether any potentially customer-sensitive data is excluded categorically.

Recommended answer:

Start with a deliberately small Git-backed corpus: decisions, plans, ADRs, curated specs, selected README/runbooks. Do not bulk-index either existing root without a file-scope review. Require citations for retrieved claims.

## Decision 8 — Tool authority and MCP policy

Need a written policy for:

- Read-only tools.
- Filesystem scopes.
- Allowed shell commands.
- Git mutations.
- GitHub writes.
- Browser access.
- Credential handling.
- Revit read vs write operations.
- Audit logs and explicit confirmation behavior.

Recommended answer:

Default deny for mutations. Start with read-only capabilities and workspace-scoped tools. Make side-effecting actions require deliberate confirmation until there is a demonstrated safe automation case.

## Decision 9 — vLLM decision criterion

Need a concrete trigger rather than ongoing debate.

Recommended policy:

Do not install/migrate to vLLM until a benchmark or required capability shows that Ollama is insufficient. Define the trial trigger as one or more of:

- Need for more than one meaningful concurrent user/agent.
- Measured throughput/latency bottleneck.
- Required model/runtime feature unsupported by Ollama.
- Measured material win on the same model and workload.
- Additional GPU capacity / a multi-user service model.

---

# Suggested immediate next actions

1. Review and explicitly split the scopes:
   - `AI-Server/mybuddy`: dedicated inference infrastructure.
   - `Personal AI Workspace`: UI, agents, curated knowledge, and tools.

2. Edit/lock the north star:
   - Keep infrastructure constraints intact.
   - State whether a private UI is an approved consumer of the server.
   - Do not implicitly turn the box into a desktop or customer-facing product service.

3. Resolve raw port exposure:
   - Decide whether to firewall/rebind raw Ollama `:11434`.
   - Keep `:11440/v1` as the only standard client endpoint.

4. Deploy a reversible private Open WebUI proof of concept:
   - Containerized.
   - Persistent storage.
   - Tailscale/LAN only.
   - Uses gateway `:11440/v1`.
   - Starts with no broad tool privileges.

5. Choose a test corpus and model-evaluation scorecard:
   - Select real prompts/tasks.
   - Capture baseline results from local candidates and existing frontier workflow.
   - Decide model aliases from measured outcomes.

6. Configure Goose on the rig for one disposable worktree:
   - Local endpoint through gateway.
   - Read-only or narrow write scope.
   - Run a controlled benchmark task set.

7. Design a minimal source-governance document before any RAG ingest:
   - Approved roots.
   - Exclusions.
   - Citation standard.
   - Re-index/deletion behavior.
   - Whether any client data is categorically blocked.

---

# Non-decisions / do not assume

- Do not assume vLLM is being adopted.
- Do not assume Open WebUI is the permanent product UI.
- Do not assume Goose replaces Claude Code/current cloud agents.
- Do not assume cloud credentials will be placed into a local UI.
- Do not assume all local files/repos will be indexed.
- Do not assume autonomous coding/deployment or unrestricted shell access.
- Do not assume OCR/client-data scope is cleared.
- Do not assume the current north star is locked; it is explicitly a draft.
- Do not use raw Ollama `:11434` as the standard client endpoint.

---

# Status matrix

| Category | Status |
|---|---|
| Dedicated inference box and authenticated API | Implemented |
| Local model bench and server constraints | Implemented / current observed state |
| Personal AI UI, Goose workflow, MCP tools, evidence retrieval | Proposed direction—not implemented |
| vLLM migration | Explicitly deferred unless evidence triggers it |
| Final product/project scope | Needs an owner decision |

---

# Recommended decision order

1. **Scope split:** Approve `mybuddy` as infrastructure and a separate Personal AI Workspace consumer project.
2. **Security:** Close or restrict raw `:11434` exposure before expanding normal access.
3. **Cockpit POC:** Approve Open WebUI as a temporary/private evaluation UI, not a permanent commitment.
4. **Agent benchmark:** Approve Goose-on-rig in disposable worktrees against a defined task set.
5. **Evidence policy:** Define curated RAG sources and citation rules before indexing anything.
6. **Tools policy:** Define permission boundaries before MCP, shell, Git, browser, GitHub, or Revit control.
7. **Model routing:** Decide whether initial cloud access is absent, manual user-choice, or eventually automatic.
8. **vLLM criterion:** Codify the measurable condition that would justify a trial.

---

# Important correction to preserve

The existing north-star draft says “no vLLM unless single-user stops being true” and that the box is a stable measurement instrument, not a generalized desktop or client deployment host.

The UI/agent direction discussed here does not overturn that. It adds a possible private, internal consumer of the endpoint—provided it remains behind the existing authenticated API boundary and does not contaminate the box’s role with uncontrolled desktop workloads, broad data ingestion, or premature production automation.
