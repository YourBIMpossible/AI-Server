# WP-E — Serving & ops hardening

**Goal:** make the endpoint production-grade on the box (and dev-friendly on the rig).
**Depends on:** WP-A.

## Deliverables

> **Runner-neutrality (2026-09-11).** Every check below asserts the *portable* surface
> (`GET /v1/models`), not a runner-native path, so the same ops layer still holds if the
> WP-H bakeoff replaces Ollama. Runner-native calls are allowed only as enrichment that
> degrades cleanly — see `scripts/aiserver_status.py` for the pattern.

- **Container:** `docker-compose.yml` healthcheck on `GET /v1/models` (done 2026-09-11, along
  with the serving-layer env). Still to add: a `model-preload` init step that pulls
  `config/models.txt` on first boot, and a `scripts/up.sh` convenience wrapper.
- **Networking (done 2026-09-12):** `scripts/setup-tailscale.sh` installs Tailscale, runs
  `tailscale up --ssh`, and firewalls `:11434` to the LAN subnet + tailnet interface via
  `ufw`. `relocate.md` documents using the box's tailnet name in `INFERENCE_BASE_URL`.
  Still open: the runner itself binds `0.0.0.0` (see `setup-linux.sh`), not the
  tailnet/LAN interface directly — `ufw` is the enforcement point for now. Binding Ollama
  itself to a specific interface is runner-specific config, revisit under WP-H if it
  matters to the winning runner.
- **Optional auth gateway:** a Caddy reverse proxy (`ops/Caddyfile`) fronting `:11434` that
  requires an API-key header. `aiserver.client.LLM` already reads `INFERENCE_API_KEY` and sends
  it as `Authorization: Bearer` — no client work left.
- **Autostart:** confirm the systemd unit (Linux) / Scheduled Task (Windows) brings the endpoint
  up at boot and survives crashes — and that the serving-layer env survives with it, verified
  from the server's own startup banner (`journalctl -u ollama`), never from the shell.
- **Endpoint-down alert:** a tiny check (reuse PC-Monitor's alert pattern) that fires if
  `/v1/models` is unreachable for N minutes.

## Acceptance

- `docker compose up -d` yields a healthy container with models preloaded.
- From the rig, `INFERENCE_API_KEY` + a tailnet `INFERENCE_BASE_URL` reach the box; a
  wrong/missing key is rejected by Caddy.
- Killing the runtime triggers the down-alert; autostart brings it back.

## Constraints

Secrets via env, never committed. Default committed config must not bind a public interface.
