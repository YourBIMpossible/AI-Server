# AI-Server — Program Plan

**Last updated:** 2026-06-16
**Status:** Active build — dev on the current rig (RTX 5080, 16GB), relocating to the dedicated 3090 box (i9-14900K / RTX 3090 24GB / 4TB NVMe).
**Companion:** hardware/build plan at `AI-Brain-Data/_status/AI-Server_Build_and_Integration_Plan.md`. A runnable scaffold + first automation already live in this repo, validated end-to-end.
**How to use this doc:** the vision + work-package map below is the program. Each core work package has a ready-to-paste Claude Code handoff in `handoffs/`. Fire the independent ones in parallel sessions.

---

## Vision

A fully-local, always-on AI automation platform you own end to end. Local models on your own GPU do the recurring, bulk, and private work — summaries, RAG over your own docs, classification, drift detection, batch dev chores — at zero per-token cost. Claude stays for heavy reasoning and the build itself. Everything is config-driven and portable: it runs on the 5080 today and moves to the 3090 box by changing one line (`OLLAMA_HOST`).

## Where we are

- **Done + validated:** Ollama runtime + OpenAI-compatible endpoint (Stage 1); `daily_digest.py` first automation (Stage 2). End-to-end tested against a mock endpoint; scripts parse; relocation path written (`relocate.md`).
- **Now:** turn the scaffold into a real platform — a shared library, RAG, an automation suite, and integration with your existing stack (Dashboard, PC-Monitor, scheduled tasks).

## Architecture (target)

```
                ┌──────── the 3090 box (later) / your 5080 (now) ────────┐
 automations ─▶ │  aiserver/ (shared lib) ─▶ Ollama ─▶ OpenAI API :11434 │
 RAG queries ─▶ │  client · config · prompts · logging   (chat + embed)  │
                └────────────────────────────────────────────────────────┘
       │                     │                          │
   out/*.md            vector store (sqlite-vec)    Dashboard tab + PC-Monitor panels
                                                    (status · GPU · last job)

 Networking: Tailscale (box reachable from the rig and off-network). Endpoint never public.
```

## Work packages

Core (build now, on the 5080) → then relocate. Optional/advanced (opt-in) listed after.

| WP | Goal | Startable now | Depends on | Handoff |
|----|------|---------------|------------|---------|
| **A — Core library** | `aiserver/` package: config/.env loader, OpenAI-compatible client (chat+embeddings), prompt templates, logging, retries. Kills the inline duplication in the current scripts. | Yes | — | `handoffs/WP-A_core-library.md` |
| **B — RAG / knowledge** | Ingest + embed AI-Brain-Data + BIMpossible docs into a local vector store; incremental re-index; query CLI with citations; doc-drift detector. | Yes | A | `handoffs/WP-B_rag-knowledge.md` |
| **C — Automation suite** | Productionize the digest; add weekly roll-up + decision→canonical drift report; a tiny job framework so new automations are drop-in. | Yes | A (B for drift) | `handoffs/WP-C_automation-suite.md` |
| **D — Integration** | Dashboard "AI Server" tab + a PC-Monitor profile for GPU/inference; offload one real scheduled task to the local endpoint. | Yes | A (C for outputs) | `handoffs/WP-D_integration.md` |
| **E — Serving & ops** | Container hardening (healthchecks, model preload), Tailscale, optional Caddy API-key, autostart, endpoint-down alerting. | Partial now, finish on box | A | outlined below |
| **F — Eval harness** | A small labeled test set; compare local output vs a Claude baseline on the digest/RAG tasks; pick per-task models on evidence. | Yes | A, B, C | outlined below |
| **G — Advanced (optimistic)** | Local Whisper meeting-note transcription; a local coding-agent for bulk chores; QLoRA fine-tune on your decision-log/writing voice (the 3090 can QLoRA small models). | Box-class | A–C | outlined below |

## Sequencing & parallelization (for Claude Code)

- **Wave 1:** build **WP-A** first — it's the only hard prerequisite, and it's short.
- **Wave 2 (parallel after A):** **WP-B**, **WP-C**, and the **PC-Monitor half of WP-D** are independent — run them in three parallel Claude Code sessions.
- **Wave 3:** **WP-D** Dashboard tab (needs C's job outputs), **WP-F** eval (needs B+C), **WP-E** finish-on-box.
- **Wave 4 (on the box):** **WP-G** advanced.

## "PC-build green light" milestone

Assemble the box once **WP-A + WP-B + WP-C are done and validated on the 5080** — i.e.:

- endpoint + shared library are solid,
- RAG answers a known question over your own docs *with citations*,
- the digest + at least one more job run unattended and clear the eval-vs-Claude bar (WP-F quick check).

At that point the box adds only **more VRAM (bigger models) + always-on dedicated hosting** — pure upside, no unknowns. That's the trigger to build it.

## Decisions to lock (recommendations)

- **Vector store:** `sqlite-vec` — single file, zero-server, matches your PC-Monitor SQLite pattern, trivially portable. (Alt: LanceDB for columnar/large-scale later.) **Rec: sqlite-vec.**
- **Embeddings:** `nomic-embed-text` served by the *same* Ollama endpoint (`/v1/embeddings`). One runtime for chat + embeddings. **Rec: yes.**
- **Package layout:** a real `aiserver/` package with `pyproject.toml`; automations import it. **Rec: yes** (ends the inline-loader duplication).
- **Scheduler:** Windows Task Scheduler now (already scripted); cron/systemd-timer on the box. Job *logic* stays OS-agnostic Python. **Rec: yes.**
- **Deps policy:** stdlib-first; a small pinned set (`sqlite-vec`, optionally `httpx`); no heavy frameworks. **Rec: yes.**

## Honesty & risks (optimistic, not naive)

- **Local ≠ Claude on hard reasoning.** Use local models for bulk/templated/private work; route hard tasks to Claude. The eval harness (WP-F) keeps this honest per task.
- **16GB → 24GB gap:** you dev on smaller models on the 5080; the box runs bigger ones. Re-check the eval bar on the box's model before trusting a job there.
- **Qwen3.6 + Ollama:** newest GGUFs need llama.cpp; default workhorse is `qwen2.5-coder:14b` until Ollama catches up (`relocate.md`).
- **Email triage** (tempting) needs Gmail API creds on the box — the Cowork Gmail connector can't be called from a headless script. Parked as optional, not core.
- **Security:** endpoint stays on the tailnet/LAN; never port-forwarded. Add an API key (Caddy) before any non-trivial exposure.

## Optional packages (opt-in — say the word and I'll break these into handoffs)

- **WP-E — Serving & ops:** productionize `docker-compose.yml` (healthcheck, model preload), Tailscale wiring, Caddy API-key gateway, autostart, a tiny endpoint-down alert (reuse PC-Monitor's alerting).
- **WP-F — Eval harness:** 15–20 labeled prompts; run each through the local model and a Claude baseline; score; produce a per-task "local OK / route to Claude" table. This is what makes "offload to local" trustworthy.
- **WP-G — Advanced:** local Whisper transcription → `AI-Brain-Data/meeting-notes/` (closes the "meeting transcription tool" item from the original plan); a local coding-agent for bulk chores (docstrings, test stubs) using the coder model; QLoRA fine-tune on your decision-logs/writing-samples so a small local model writes in your voice.

## How to pass to Claude Code

1. Open a Claude Code session in `F:\AI-Dev\AI-Server\`.
2. Paste the relevant `handoffs/WP-*.md` as the task. Each is self-contained: context, deliverables, acceptance tests, constraints.
3. House style applies — see `AI-Server/CLAUDE.md` (points to `system/WORKING-STYLE.md` + `system/SYSTEM-RULES.md`). Tests + acceptance criteria are the definition of done.
4. Independent WPs → separate parallel sessions (see the wave map).
