# WP-E — Serving & ops hardening

**Goal:** make the endpoint production-grade on the box (and dev-friendly on the rig).
**Depends on:** WP-A.

## Deliverables

- **Container:** extend `docker-compose.yml` with a healthcheck (`GET /api/tags`), a
  `model-preload` init step that pulls `config/models.txt` on first boot, and a restart policy.
  A `scripts/up.sh` convenience wrapper.
- **Networking:** `scripts/setup-tailscale.sh` (install + `tailscale up`); document using the
  box's tailnet name as `OLLAMA_HOST`. Bind Ollama to the tailnet/LAN interface — not 0.0.0.0 on
  an untrusted network.
- **Optional auth gateway:** a Caddy reverse proxy (`ops/Caddyfile`) fronting `:11434` that
  requires an API-key header; teach `aiserver.client.LLM` an optional `OLLAMA_API_KEY`.
- **Autostart:** confirm the systemd unit (Linux) / Scheduled Task (Windows) brings the endpoint
  up at boot and survives crashes.
- **Endpoint-down alert:** a tiny check (reuse PC-Monitor's alert pattern) that fires if
  `/api/tags` is unreachable for N minutes.

## Acceptance

- `docker compose up -d` yields a healthy container with models preloaded.
- From the rig, `OLLAMA_API_KEY` + tailnet `OLLAMA_HOST` reach the box; a wrong/missing key is
  rejected by Caddy.
- Killing the runtime triggers the down-alert; autostart brings it back.

## Constraints

Secrets via env, never committed. Default committed config must not bind a public interface.
