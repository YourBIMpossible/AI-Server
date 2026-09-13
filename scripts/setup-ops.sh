#!/usr/bin/env bash
# WP-E on the box: API-key gateway, boot-time warm-up, endpoint-down watch. Needs root.
#
#   sudo bash scripts/setup-ops.sh            # install and start; direct :11434 still reachable
#   sudo bash scripts/setup-ops.sh --enforce  # also make the gateway the ONLY network path
#
# --enforce swaps the ufw rules: the gateway port opens to the LAN subnet + tailnet, and the
# runner's :11434 rules are removed, so the runner stays reachable on loopback only. Every
# client (the rig's .env) must then use the gateway URL and INFERENCE_API_KEY -- which is why
# it is a separate, explicit step.
#
# Reversible: systemctl disable --now aiserver-gateway aiserver-endpoint-watch.timer
# aiserver-preload; ufw rules as printed below.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
CADDY_VERSION=2.11.4
PORT=11440
ENFORCE=0
[ "${1:-}" = "--enforce" ] && ENFORCE=1

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

echo "=== 1. Caddy $CADDY_VERSION (checksum-verified) ==="
if /usr/local/bin/caddy version 2>/dev/null | grep -q "^v$CADDY_VERSION "; then
  echo "already installed"
else
  tmp="$(mktemp -d)"
  base="https://github.com/caddyserver/caddy/releases/download/v$CADDY_VERSION"
  tarball="caddy_${CADDY_VERSION}_linux_amd64.tar.gz"
  curl -fsSL -o "$tmp/$tarball" "$base/$tarball"
  curl -fsSL -o "$tmp/sums" "$base/caddy_${CADDY_VERSION}_checksums.txt"
  (cd "$tmp" && grep " $tarball\$" sums | sha512sum -c -)
  tar -xzf "$tmp/$tarball" -C "$tmp" caddy
  install -m 755 "$tmp/caddy" /usr/local/bin/caddy
  rm -rf "$tmp"
fi

echo "=== 2. Gateway key and bind addresses ==="
install -d -m 755 /etc/ai-server
LAN_IP="$(ip -o -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
# Refuse anything that isn't loopback, private (RFC1918) or tailnet (CGNAT) -- never a public bind.
for ip in $LAN_IP $TS_IP; do
  python3 - "$ip" <<'EOF'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
ok = ip.is_loopback or ip.is_private or ip in ipaddress.ip_network("100.64.0.0/10")
sys.exit(0 if ok else f"refusing to bind non-private address {ip}")
EOF
done
if [ -f /etc/ai-server/gateway.env ]; then
  echo "keeping existing /etc/ai-server/gateway.env"
else
  ( umask 077
    cat > /etc/ai-server/gateway.env <<EOF
INFERENCE_API_KEY=$(openssl rand -hex 32)
GATEWAY_BIND=127.0.0.1 ${LAN_IP} ${TS_IP}
GATEWAY_PORT=$PORT
GATEWAY_UPSTREAM=127.0.0.1:11434
EOF
  )
  echo "wrote /etc/ai-server/gateway.env (binds: 127.0.0.1 ${LAN_IP} ${TS_IP})"
fi
chmod 600 /etc/ai-server/gateway.env
install -m 644 "$ROOT/ops/Caddyfile" /etc/ai-server/Caddyfile

echo "=== 3. systemd units ==="
for u in aiserver-gateway.service aiserver-preload.service aiserver-endpoint-watch.service aiserver-endpoint-watch.timer; do
  sed -e "s#@REPO@#$ROOT#g" -e "s#@USER@#$RUN_USER#g" "$ROOT/ops/systemd/$u" > "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable aiserver-gateway.service aiserver-endpoint-watch.timer aiserver-preload.service
# restart, not start: a re-run must pick up a changed Caddyfile or unit
systemctl restart aiserver-gateway.service
systemctl start aiserver-endpoint-watch.timer

echo "=== 4. Verify the gateway ==="
# gateway.env is a systemd EnvironmentFile (KEY=value, value taken verbatim, spaces included).
# Never source it as shell: GATEWAY_BIND holds several space-separated addresses.
INFERENCE_API_KEY="$(sed -n 's/^INFERENCE_API_KEY=//p' /etc/ai-server/gateway.env | head -1)"
sleep 2
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
no_key="$(code "http://127.0.0.1:$PORT/v1/models")"
bad_key="$(code -H 'Authorization: Bearer wrong' "http://127.0.0.1:$PORT/v1/models")"
good_key="$(code -H "Authorization: Bearer $INFERENCE_API_KEY" "http://127.0.0.1:$PORT/v1/models")"
native="$(code -H "Authorization: Bearer $INFERENCE_API_KEY" "http://127.0.0.1:$PORT/api/tags")"
echo "no key: $no_key (want 401) · wrong key: $bad_key (want 401) · right key: $good_key (want 200) · /api/tags: $native (want 404)"
[ "$no_key" = 401 ] && [ "$bad_key" = 401 ] && [ "$good_key" = 200 ] && [ "$native" = 404 ] || {
  echo "Gateway verification FAILED -- see: journalctl -u aiserver-gateway" >&2
  exit 1
}

if [ "$ENFORCE" = 1 ]; then
  echo "=== 5. Enforce: gateway is the only network path ==="
  LAN_IFACE="$(ip route show default | awk '/default/ {print $5; exit}')"
  LAN_NET="$(python3 -c "import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)" \
    "$(ip -o -f inet addr show "$LAN_IFACE" | awk '{print $4}' | head -1)")"
  ufw allow from "$LAN_NET" to any port "$PORT" proto tcp comment 'ai-server gateway: LAN'
  ufw allow in on tailscale0 to any port "$PORT" proto tcp comment 'ai-server gateway: tailnet'
  ufw delete allow from "$LAN_NET" to any port 11434 proto tcp || true
  ufw delete allow in on tailscale0 to any port 11434 proto tcp || true
  ufw status verbose | grep -E "$PORT|11434|Status"
  echo "Undo: ufw allow from $LAN_NET to any port 11434 proto tcp; ufw allow in on tailscale0 to any port 11434 proto tcp"
fi

echo
echo "Done. Clients: INFERENCE_BASE_URL=http://<box tailnet name or LAN IP>:$PORT/v1"
echo "               INFERENCE_API_KEY=<the value in /etc/ai-server/gateway.env>   (sudo cat it; never commit it)"
