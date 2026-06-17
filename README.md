# AI-Server

![CI](https://github.com/YourBIMpossible/AI-Server/actions/workflows/ci.yml/badge.svg)

A portable local-LLM inference stack: an always-on, OpenAI-compatible endpoint your
automations call. Built to **run on your current rig (RTX 5080) now** and **relocate to the
dedicated 3090 box** later by changing one line.

**Design principle:** the runtime (Ollama) and the automations are decoupled. Only
`OLLAMA_HOST` and the model name differ between machines; every script and config moves
unchanged. The automations run wherever your files are (your main rig) — relocating just
points them at the box's GPU.

## Run here now (Windows, RTX 5080)

```powershell
cd F:\AI-Dev\AI-Server
copy .env.example .env
# 1. install Ollama + pull models + smoke test
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
# 2. first automation: schedule the daily digest
powershell -ExecutionPolicy Bypass -File .\automation\register-task-windows.ps1
```

After step 1 you have a local endpoint at `http://localhost:11434/v1`, and the smoke test
confirms it answers.

## What you get

- **Stage 1 — endpoint:** Ollama serving a workhorse model on the 5080.
- **Stage 2 — first automation:** `daily_digest.py` summarizes the last week of `01_BuildLog/`
  + `decision-log/` into a digest, on local inference, at no Claude usage cost.
- **Stage 3 — RAG (next build):** the embeddings model is pre-pulled; the indexer comes next.

## Move to the 3090 box later

See `relocate.md`. Short version: run `scripts/setup-linux.sh` on the box, then set
`OLLAMA_HOST=http://<box>:11434` in `.env`. Nothing else changes.

## Layout

```
README.md                     this file
.env.example                  config: endpoint, model, workspace paths
config/models.txt             models to pull (rig vs box notes inside)
scripts/
  setup-windows.ps1           install + pull + smoke test (current rig)
  setup-linux.sh              same, for the 3090 box (Ubuntu)
  smoke-test.py               hit the endpoint, print a completion
automation/
  daily_digest.py             Stage-2 first automation
  register-task-windows.ps1   schedule the digest daily
docker-compose.yml            optional containerized runtime (for the box)
relocate.md                   exact move-to-3090 steps
```

## Notes

- Defaults target the 5080's 16GB. The 3090's 24GB runs bigger models — swap in
  `config/models.txt` / `.env` (notes inside).
- The newest Qwen3.6 GGUFs don't load in Ollama yet; the default workhorse is
  `qwen2.5-coder:14b`. On the box you can run llama.cpp for Qwen3.6, or step up to
  `qwen2.5-coder:32b` / `llama3.3:70b`.
- Keep the endpoint on your LAN — don't port-forward it to the internet. Prefer Tailscale.
