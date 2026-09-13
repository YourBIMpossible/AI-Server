# NORTHSTAR closeout check

**Date:** 2026-09-13 · **Box:** `mybuddy` · **Scope:** the five "What done looks like" bullets in `NORTHSTAR.md`, checked live over `ssh mybuddy`. Read-only, except fast-forwarding `~/AI-Server` to `c135da1`. Afterwards the owner wrote the box's `~/AI-Server/.env`.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Up, survives reboot, OpenAI API over Tailscale, verified from the banner | **Met** | After the owner installed Tailscale on the rig, `GET http://100.89.51.34:11434/v1/models` from the rig returned 200 over the tailnet. Boot 0 started 06:51:58 UTC, after WP-E was installed at 06:28. This boot's journald banner shows `OLLAMA_FLASH_ATTENTION:true`, `OLLAMA_CONTEXT_LENGTH:32768`, keep-alive -1, `OLLAMA_MODELS:/srv/models`, `Listening on [::]:11434 (version 0.34.0)`, and the RTX 3090 as CUDA0. The gateway listens on `127.0.0.1`, `192.168.1.128` and `100.89.51.34` `:11440`. Probed from the box's tailnet IP: `:11434` gives 200 and `:11440` gives 401 without a key. The endpoint-watch timer fires every minute. The units run from `~/AI-Server/scripts`, so the worktree-path flag in WP-E is resolved. |
| 2 | Phase 0 re-run on the box | **Met** | `decisions/2026-09-13__box-phase0-remeasure.md` |
| 3 | One real automation unattended, clears WP-F | **Met, with a caveat** | `daily-digest` passed under rubric v2 (`decisions/2026-09-13__wp-h-runner-bakeoff.md`). That run used the bakeoff's shared `qwen3moe` Q4_K_M artifact, not the model pick gemma4, so it is not evidence for gemma4. It was launched by a *transient* timer. No installed schedule exists on the box. |
| 4 | Model choice is a config line backed by an eval score | **Met** | The pick `gemma4:26b-a4b-it-q4_K_M` (27/27) is in `config/models.txt`. The rig's `.env` sets `INFERENCE_MODEL=gemma4:26b-a4b-it-q4_K_M`. The box's `~/AI-Server/.env` (mode 600) now sets the same line, and `load_config()` on the box resolves `model='gemma4:26b-a4b-it-q4_K_M'`. |
| 5 | Runner chosen by the bakeoff; swap proven a deployment change | **Met** | The WP-H migration acceptance passed both conditions. The decision to keep Ollama is recorded in `decisions/2026-09-13__runner-and-model-pick.md`. |

## Left for the owner

1. **Criterion 3 caveat, optional:** install a persistent timer for `daily-digest` if "unattended" should mean an installed schedule rather than a transient one.

## Flags

- **The box's `WORKSPACE` falls back to a Windows path.** The box `.env` sets only the model, so `load_config()` gives `workspace='F:\BIMpossible-Workspace'`. A digest job run on the box needs `WORKSPACE` set to a real box path.
- **The rig's `.env` still uses the LAN URL.** `INFERENCE_BASE_URL` is `http://192.168.1.128:11434/v1`, which works only at home. For access away from home, switch it to `http://100.89.51.34:11434/v1`.
- **Ollama listens on every interface.** The banner shows `OLLAMA_HOST:http://0.0.0.0:11434`, so `:11434` answers without a key on the LAN and tailnet. `--enforce` stays off per the runner-pick decision. That call is settled.
- **Cloud features are enabled in the banner.** It shows `OLLAMA_NO_CLOUD:false` and `OLLAMA_REMOTES:[ollama.com]`. This is not exposure, but it sits oddly with "fully local".
