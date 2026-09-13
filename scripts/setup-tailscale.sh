#!/usr/bin/env bash
# Install Tailscale on the 3090 box and firewall the inference port.
#
# Run this during initial box setup, even if you plan to use the LAN address in
# INFERENCE_BASE_URL for now. The alternative -- installing it later, "when you actually
# need remote access" -- means a second trip to a box with no monitor attached, for a job
# that takes five minutes today because you're already at a terminal here. Tailscale sits
# idle until you point .env at the tailnet name; nothing about running it changes how the
# LAN path behaves.
#
# What this does NOT do: change OLLAMA_HOST, touch .env, or pick which address your
# clients use. That's a one-line edit in .env, made when you decide to make it -- see the
# printed instructions at the end.
set -euo pipefail

echo "=== Tailscale install ==="
if command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale already installed ($(tailscale version | head -1))."
else
  curl -fsSL https://tailscale.com/install.sh | sh
fi

echo
echo "=== tailscale up ==="
echo "This opens a login URL -- follow it in a browser (on any device) to authorize this"
echo "machine against your Tailscale account. --ssh also exposes SSH over the tailnet,"
echo "which is worth having once this box has no monitor attached."
sudo tailscale up --ssh

TAILNET_IP="$(tailscale ip -4 2>/dev/null || true)"
TAILNET_NAME="$(tailscale status --self --json 2>/dev/null | grep -o '"DNSName":"[^"]*"' | head -1 | cut -d'"' -f4 | sed 's/\.$//' || true)"

if [ -z "$TAILNET_IP" ]; then
  echo "WARNING: could not read a tailnet IP back from 'tailscale ip -4'."
  echo "Run 'tailscale status' by hand and confirm this device shows up before continuing."
fi

# --- Firewall: LAN + tailnet only, on 11434 ---
#
# scripts/setup-linux.sh binds Ollama to 0.0.0.0:11434 -- every interface, including
# whatever this box's public-facing interface turns out to be if one ever exists. Its own
# comment says to firewall this; nothing did until now. ufw is the one piece of this file
# that matters even if you never touch Tailscale again -- it's what makes "LAN-only for
# now" a real boundary instead of a hope.
echo
echo "=== Firewalling :11434 to LAN + tailnet only (ufw) ==="
if ! command -v ufw >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y ufw
fi

# Detect the LAN subnet from the default route's interface, rather than hard-coding
# 192.168.1.0/24 -- this script has to work on whatever network the box actually lands on.
LAN_IFACE="$(ip route show default | awk '/default/ {print $5; exit}')"
LAN_CIDR="$(ip -o -f inet addr show "$LAN_IFACE" 2>/dev/null | awk '{print $4}' | head -1)"
if [ -n "$LAN_CIDR" ]; then
  # Derive the network address from the interface CIDR (e.g. 192.168.1.98/24 -> 192.168.1.0/24)
  LAN_NET="$(python3 -c "import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)" "$LAN_CIDR")"
  sudo ufw allow from "$LAN_NET" to any port 11434 proto tcp comment 'ai-server: LAN'
  echo "Allowed from LAN: $LAN_NET"
else
  echo "WARNING: could not detect the LAN subnet from interface '$LAN_IFACE'."
  echo "Add the rule by hand: sudo ufw allow from <your-lan-cidr> to any port 11434 proto tcp"
fi

sudo ufw allow in on tailscale0 to any port 11434 proto tcp comment 'ai-server: tailnet'
echo "Allowed from tailnet: tailscale0"

# Enable ufw if this is the first rule ever added on this box. Non-interactive so this
# script can run unattended; --force skips the "this may disrupt SSH" prompt, which is
# safe here because we've already allowed the LAN net and tailscale0 above (and sshd's
# own rule, if ufw was already active, is untouched by any of this).
if sudo ufw status | grep -q "Status: inactive"; then
  echo "ufw was inactive -- enabling it now with the rules above (plus OpenSSH, if installed)."
  sudo ufw allow OpenSSH || true
  sudo ufw --force enable
else
  sudo ufw reload
fi

echo
sudo ufw status verbose | grep -E '11434|Status'

echo
echo "=== Done ==="
if [ -n "$TAILNET_NAME" ]; then
  echo "Tailnet name: $TAILNET_NAME"
  echo "Tailnet IP:   $TAILNET_IP"
else
  echo "Tailnet IP:   ${TAILNET_IP:-<unknown -- check 'tailscale status'>}"
fi
cat <<EOF

Nothing about how the endpoint answers changed. To actually route your rig's traffic over
the tailnet instead of the LAN, edit .env on the rig:

  INFERENCE_BASE_URL=http://${TAILNET_NAME:-<this-box-tailnet-name>}:11434/v1

Until you make that edit, the LAN address keeps working exactly as it did before this
script ran -- this only added a second, currently-unused path in, plus the firewall rule
that was already overdue regardless of which path you use.
EOF
