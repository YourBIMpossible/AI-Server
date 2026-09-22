# Box state check and the chat-UI pilot

**Date:** 2026-09-16 · **Box:** `mybuddy` · **Method:** read-only survey over `ssh mybuddy`
(ports, units, journals, compose files with secrets redacted, HTTP probes). Nothing on the box
was changed. First look at the box since the 2026-09-13 closeout.

## Endpoint: still meets the closeout bar

| Check | Result |
|---|---|
| Uptime | 3d 8h — no reboot since the closeout boot of 09-13 |
| Ollama | `ollama.service` running, 0.34.0, `*:11434`; `/v1/models` lists 8 models |
| Gateway | `aiserver-gateway.service` running (Caddy), `:11440` on `127.0.0.1`, `<box-lan-ip>`, `<box-tailnet-ip>`; no warnings in the journal since 09-13 |
| Watch timer | `aiserver-endpoint-watch.timer` active, every minute |
| Preload | `aiserver-preload.service` enabled; ran once at boot (oneshot) |
| Units | All `ExecStart` lines point at `/home/zetard/AI-Server/scripts/…` — off the worktree path, as recorded 09-13 |
| Box `.env` | Only `INFERENCE_MODEL` set (still `gemma4:26b-a4b-it-q4_K_M` per closeout) |
| Repo on box | `~/AI-Server` at `c135da1` (WP-I, #19). `origin/main` is now `c578e69` (#20 closeout merge) — box is one merge behind |
| GPU | RTX 3090, 21 MiB used, idle. **No model resident.** `/api/ps` is empty |
| Headroom | 61 GB RAM (57 available), 32 threads, load 0.15; `/` 58 GB of 466 GB used; `/srv/models` 108 GB |

**Model is cold.** The closeout banner had keep-alive `-1`, but a per-request `keep_alive`
overrides the server default. `~/ollama-benchmark.py` (see below) sends `keep_alive: "1h"`,
so after its 06:12 run the model unloaded around 07:12 and nothing has re-warmed it. The next
real request pays the cold load. `preload.py` only runs at boot. Not a regression — a
behaviour to know: any client that sets `keep_alive` decides residency for everyone.

## Models on the box (all pulled 2026-09-13, 00:57–02:07)

`gemma4:26b-a4b-it-q4_K_M` (the pick) · `gemma4:31b-it-q4_K_M` · `qwen3.8:27b-q4_K_M` ·
`qwen3.5:9b` · `qwen3-coder:30b-a3b-q4_K_M` · `qwen2.5-coder:14b` ·
`nemotron-3.5-lightning:30b-a3b-q4_K_M` · `nomic-embed-text:latest`.

Four of these (`gemma4:31b`, `qwen3.8:27b`, `qwen3.5:9b`, `nemotron-3.5-lightning`) have no
WP-F eval score on record. They are candidates, not picks, until `eval/` scores them on the
box. The pick stays `gemma4:26b-a4b-it-q4_K_M` (27/27, `decisions/2026-09-13__runner-and-model-pick.md`).

## Ad-hoc benchmark outside the harness

`~/ollama-benchmark.py` and `~/ai_stress_test.csv` (157 `nvidia-smi` samples, 09-16
05:53–06:12) benchmark `nemotron-3.5-lightning` directly against `/api/generate` with two
prompts (warm-short 128 tok, long-prompt ~140× repeated background + 160 tok). Peak VRAM in
the CSV: 22.7 GB of 24 GB. These numbers live only in the home directory — not in `eval/`,
no batch identity, not comparable to the WP-F/Phase-0 records. Useful as a smoke signal
(the 30B-A3B fits with ~1.3 GB to spare), not as evidence for a model decision.

## The chat-UI pilot: `~/mybuddy-pilot/`

Three chat front-ends were installed on 2026-09-16 (~03:57–06:12), all Docker, all bound to
**localhost only**, data under `/srv/data/mybuddy-pilot/` (root-owned):

| App | Port | Image | Talks to the model via | Notes |
|---|---|---|---|---|
| Open WebUI | `127.0.0.1:3000` | `ghcr.io/open-webui/open-webui:main` (v0.11.3) | `OLLAMA_BASE_URL=http://host.docker.internal:11434` | Auth on, signup off. `/api/config` answers |
| AnythingLLM | `127.0.0.1:3001` | `mintplexlabs/anythingllm:latest` | not visible in compose — set inside the app's own settings | `cap_add: SYS_ADMIN` (its built-in browser scraper). `/api/ping` online. Storage dir empty from outside (root-only) |
| LibreChat | `127.0.0.1:3080` | `librechat-dev:latest` from a full source clone at `385c6f8a1` | `OLLAMA_BASE_URL` in `.env`, used for **RAG embeddings only** (`EMBEDDINGS_PROVIDER=ollama`) | Brings `mongo:8.0.20`, `meilisearch v1.35.1`, `pgvector pg15`, `rag_api`, `admin-panel`. `ALLOW_REGISTRATION=true`. **No `librechat.yaml` exists and none is mounted**, so no chat endpoint for the local model is configured — LibreChat can embed with Ollama but, as installed, has nothing to chat with. Unverified from outside (the config API needs a login) |

All three bypass the API-key gateway (`:11440`) and hit Ollama directly on `:11434` via the
Docker bridge. That is fine while they bind to `127.0.0.1`; it becomes a gap the moment one is
exposed on the LAN or tailnet — the gateway would have to sit in front, or the app would need
`INFERENCE_API_KEY`.

Reaching them today means an SSH tunnel (`ssh -L 3000:127.0.0.1:3000 mybuddy`) or the
tailnet plus a tunnel. Nothing new is exposed. **No public exposure** holds.

`docker` needs `sudo` on this box (`zetard` is not in the `docker` group) — a deliberate
posture, so a script on the box cannot enumerate or restart the containers without a
password. Container run state was confirmed only by HTTP (all three answer 200).

## What this changes for the mission

Nothing in "What done looks like" moved. Two things to watch:

1. **Instrument load.** LibreChat's stack (Mongo + Meilisearch + Postgres + a RAG API) runs
   permanently. Today it is idle (load 0.15), but any eval run should record whether the
   pilot was up. Batch identity already carries the hardware profile; it should carry
   "pilot containers running: yes/no" too, or evals should run with the pilot stopped.
2. **Residency.** A chat UI that sends its own `keep_alive` (Open WebUI does, per
   conversation) will evict whatever `preload.py` warmed. The working model's residency is
   no longer under the endpoint's control alone.

## Housekeeping seen, not done

- Box `~/AI-Server` is one merge behind `origin/main` (`c135da1` → `c578e69`).
- Old worktrees still present on the box: `box-mission`, `box-phase0`, `box-wrapup` — all
  merged.
- `~/ollama-benchmark.py` / `~/ai_stress_test.csv` sit loose in the home directory; if the
  numbers matter, they belong in `eval/` as a scored case with batch identity.
