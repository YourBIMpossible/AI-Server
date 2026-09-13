# NORTHSTAR closeout check

**Date:** 2026-09-13 · **Box:** `mybuddy` · **Scope:** the five "What done looks like" bullets in `NORTHSTAR.md`, checked live over `ssh mybuddy`. Read-only, except fast-forwarding `~/AI-Server` to `c135da1`.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Up, survives reboot, OpenAI API over Tailscale, verified from the banner | **Met** | Boot 0 started 06:51:58 UTC, after WP-E was installed at 06:28. This boot's journald banner shows `OLLAMA_FLASH_ATTENTION:true`, `OLLAMA_CONTEXT_LENGTH:32768`, keep-alive -1, `OLLAMA_MODELS:/srv/models`, `Listening on [::]:11434 (version 0.34.0)`, and the RTX 3090 as CUDA0. The gateway listens on `127.0.0.1`, `192.168.1.128` and `100.89.51.34` `:11440`. Probed from the box's tailnet IP: `:11434` gives 200 and `:11440` gives 401 without a key. The endpoint-watch timer fires every minute. The units run from `~/AI-Server/scripts`, so the worktree-path flag in WP-E is resolved. |
| 2 | Phase 0 re-run on the box | **Met** | `decisions/2026-09-13__box-phase0-remeasure.md` |
| 3 | One real automation unattended, clears WP-F | **Met, with a caveat** | `daily-digest` passed under rubric v2 (`decisions/2026-09-13__wp-h-runner-bakeoff.md`). It was launched by a *transient* timer. No installed schedule exists on the box. |
| 4 | Model choice is a config line backed by an eval score | **Not met in effect** | The pick `gemma4:26b-a4b-it-q4_K_M` (27/27) is in `config/models.txt`. The box has no `.env`, so `INFERENCE_MODEL` falls back to the default `qwen2.5-coder:14b`, and boot preload warmed `qwen2.5-coder:14b`. |
| 5 | Runner chosen by the bakeoff; swap proven a deployment change | **Met** | The WP-H migration acceptance passed both conditions. The decision to keep Ollama is recorded in `decisions/2026-09-13__runner-and-model-pick.md`. |

## Left for the owner

1. **Criterion 4:** on the box, run `printf 'INFERENCE_MODEL=gemma4:26b-a4b-it-q4_K_M\n' > ~/AI-Server/.env && chmod 600 ~/AI-Server/.env`, then `python3 ~/AI-Server/scripts/preload.py`. The assistant's attempt to write box config was blocked by the permission classifier.
2. **Criterion 3 caveat, optional:** install a persistent timer for `daily-digest` if "unattended" should mean an installed schedule rather than a transient one.

## Flags

- **The rig can't reach the tailnet.** The rig has no `tailscale` CLI, and `100.89.51.34` timed out from the rig. The LAN URL `http://192.168.1.128:11434` answers 200.
- **Ollama listens on every interface.** The banner shows `OLLAMA_HOST:http://0.0.0.0:11434`, so `:11434` answers without a key on the LAN and tailnet. `--enforce` stays off per the runner-pick decision. That call is settled.
- **Cloud features are enabled in the banner.** It shows `OLLAMA_NO_CLOUD:false` and `OLLAMA_REMOTES:[ollama.com]`. This is not exposure, but it sits oddly with "fully local".
