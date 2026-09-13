# WP-E — endpoint up and reliable: what landed, what's verified, what still needs root

**Date:** 2026-09-13 · **Box:** `mybuddy` · **Branch:** `box-mission`

## TL;DR

- **Gateway is live on the box:** Caddy 2.11.4 listens on 127.0.0.1, the LAN address and the tailnet address at `:11440`. It requires `Authorization: Bearer $INFERENCE_API_KEY`, proxies `/v1/*` only, and refuses to start with a short key. Verified: no key 401, wrong key 401, right key 200 plus completion plus streaming, `/api/tags` 404.
- **Not yet enforced:** `:11434` is still reachable directly from LAN and tailnet. `setup-ops.sh --enforce` swaps the ufw rules, and it breaks the rig until its `.env` moves to `:11440` plus the key.
- **Endpoint-down alert** runs every minute (systemd timer) and **boot warm-up** is enabled.
- **Crash recovery passes:** SIGKILL → serving again in 7.25 s (completion in ≤13.82 s), banner env intact; the down-alert fired at 60 s and cleared 3.5 s after restart. **Post-install reboot check: pending** (needs the owner to reboot; this session cannot).

## Landed (commits `52dc6db`, `0b8b6a1`)

| Piece | File | Behaviour |
|---|---|---|
| API-key gateway | `ops/Caddyfile`, `ops/systemd/aiserver-gateway.service` | Bearer key match; `/v1/*` proxied with streaming (`flush_interval -1`, 15 min response timeout); everything else 401/404. Every value comes from `/etc/ai-server/gateway.env`; the committed default binds loopback. The unit refuses a missing key or one under 32 chars (an empty key would match `Bearer `). DynamicUser, ProtectSystem=strict. |
| Installer | `scripts/setup-ops.sh` (root) | Checksum-verified Caddy. Key from `openssl rand -hex 32`, kept on re-runs. Bind addresses must be loopback, RFC1918 or tailnet CGNAT, otherwise it refuses. Units are templated with the repo path. Verifies 401/401/200/404. `--enforce` for the ufw swap. |
| Warm-up | `scripts/preload.py`, `scripts/up.sh`, `aiserver-preload.service` | Waits for `/v1/models`, best-effort pull of `config/models.txt` via the runner CLI, 1-token warm of `INFERENCE_MODEL`. |
| Down alert | `scripts/endpoint_watch.py`, `aiserver-endpoint-watch.{service,timer}` | Portable check (`/v1/models`). One `ALERT` after `ENDPOINT_ALERT_MINUTES` (default 3), one `RECOVERED`, journald priority prefixes, optional LAN webhook. `--generate` exists but is off in the timer: on 24 GB it would reload a model every minute. |
| Crash test | `scripts/crash-recovery-test.sh` (root) | SIGKILL the runner's main PID, then time to active, to `/v1/models` 200 and to a successful completion, and check the new banner still has FA / 32768 / keep-alive / model store. Then stop the runner past a 1-minute alert window: ALERT must fire, then RECOVERED. Writes `out/ops/crash-recovery-*.json`. |

New config keys (in `.env.example`): `EVAL_JUDGE_MODEL`, `ENDPOINT_ALERT_MINUTES`, `ENDPOINT_ALERT_WEBHOOK`. No runner name appears in any client-facing key.

## Verified on the box

- **Local check before install:** Caddy on loopback with a throwaway key, `aiserver.client.LLM` as the client. Missing and wrong keys raise `LLMError` with HTTP 401; the right key gave `ping()` True, a completion, and SSE streaming chunks.
- **Owner's `sudo bash scripts/setup-ops.sh` (2026-09-13 06:17 UTC):**
  - The run aborted at its verify step: the step sourced `gateway.env` as shell and executed an IP address. Fixed in `0b8b6a1` by reading the key with `sed`; re-runs are safe and keep the key.
  - The gateway had already started: active, 0 restarts, listening on `127.0.0.1`, `192.168.1.128` and `100.89.51.34:11440`, 401 without a key on all three.
  - Direct `127.0.0.1:11434` is still 200; nothing user-facing broke.
  - The endpoint-watch timer fires each minute and exits clean.
- **Tests:** `tests/test_ops.py` covers the alert state machine (one alert per outage, blips never alert, a 0 timestamp is a real value), preload against the stdlib mock, and config guards (private default bind, `/v1` only, no sourcing, key kept).

## Crash recovery — **passes** (owner ran `sudo bash scripts/crash-recovery-test.sh`, 06:43 UTC)

| Phase | Result |
|---|---|
| A — SIGKILL the runner's main PID | unit active again after **3.62 s**, `/v1/models` 200 after **7.25 s**, a completion on `qwen2.5-coder:14b` after **13.82 s**; the new startup banner still carries FA, 32768, keep-alive -1, `/srv/models` |
| B — stop the runner past a 1-minute window | `ALERT` fired after **60.41 s** of downtime; `RECOVERED` **3.5 s** after the start |

Numbers come from the owner's terminal: the script's final JSON step crashed on a
`SyntaxError` because it pasted the raw banner into a shell-expanded Python heredoc. Fixed
(values now cross via the environment; a test guards it). Caveat on Phase A: it overlapped
with this session's last llama-server run on the GPU, so 13.82 s to completion is an upper
bound, not a clean figure. The setup-ops re-run the same hour was clean: 401 / 401 / 200 / 404.

## Not verified — needs the owner

1. Reboot. Then confirm from this boot's journald that the Ollama banner still carries FA, 32768, keep-alive -1 and `/srv/models`, the gateway is up on all three binds, preload warmed `INFERENCE_MODEL`, and the watch timer runs.
2. Decide on `--enforce`. Then set the rig's `.env` to `INFERENCE_BASE_URL=http://<tailnet name>:11440/v1` plus `INFERENCE_API_KEY` from `sudo cat /etc/ai-server/gateway.env`. Never commit the key.

## Flags

- The preload and watch units point at `…/.claude/worktrees/box-mission/scripts/`, because setup ran from that worktree. Re-run `setup-ops.sh` from `~/AI-Server` after merging, or the units break when the worktree is removed.
- Plain HTTP on the LAN: the key crosses the LAN unencrypted. Tailscale encrypts the tailnet path. Prefer the tailnet URL on the rig.
- `ENDPOINT_ALERT_WEBHOOK` is unset, so alerts go to journald only (`journalctl -p crit -u aiserver-endpoint-watch`). PC-Monitor's alert channel is not on the box.
- The compose `model-preload` init container from the handoff is not built. The box runs Ollama under systemd, not Docker; `up.sh --compose` is untested (no Docker here).
