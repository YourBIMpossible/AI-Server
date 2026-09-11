#!/usr/bin/env bash
# AI-Server setup for the dedicated 3090 box (Ubuntu).
# Installs Ollama, exposes it on the LAN, pulls models, runs a smoke test.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "AI-Server root: $ROOT"

# 1. Install Ollama (official script).
if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "Ollama already installed."
fi

# 2. Serving-layer configuration.
#
# These are NOT cosmetic. Measured on the RTX 5080 rig (Local Intel phase 0, 2026-09-06):
# flash attention off vs on moved prefill from 1.9 tok/s to 288 tok/s -- ~150x. Ollama's
# context default is still 4096, which silently truncates the ~27k-token prompts the log
# and digest jobs send. A default install here is a disabled code path, and any benchmark
# taken against one is measuring the wrong thing.
#
# KV cache is left at f16 on purpose: the "q8_0 is nearly free" claim has no rigorous
# public measurement, and none for citation-grounded extraction. 24GB does not force the
# tradeoff at 32k, so don't take it.
echo "Configuring the Ollama service (LAN bind + serving-layer env)..."
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
# Reachable from the main rig. Firewall this to the LAN/Tailscale interface --
# never port-forward 11434 to the public internet.
Environment="OLLAMA_HOST=0.0.0.0:11434"
# ~150x on prefill. Explicit even though recent Ollama enables it when supported.
Environment="OLLAMA_FLASH_ATTENTION=1"
# Default is 4096; long-context jobs need this or they are silently truncated.
Environment="OLLAMA_CONTEXT_LENGTH=32768"
# Keep the model resident. Local models are approved for warm sessions only
# (Local Intel decision, 2026-09-06) -- cold start is explicitly not guaranteed.
Environment="OLLAMA_KEEP_ALIVE=-1"
# Single-user box: no concurrency to win, and parallel slots split the KV cache.
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama || true

# 2b. Verify what the SERVER PROCESS actually sees.
#
# Verify the banner, never the shell. A shell's view of the environment is not the
# service's -- that mismatch already invalidated a full measurement batch on the rig
# (Local Intel runtime-identity amendment, 2026-09-06). Ollama logs its effective
# configuration at startup; that log is the only source of truth here.
echo
echo "Effective server configuration (from the service's own startup banner):"
sleep 2
if ! sudo journalctl -u ollama --since "1 min ago" --no-pager 2>/dev/null \
     | grep -oE 'OLLAMA_(FLASH_ATTENTION|CONTEXT_LENGTH|KEEP_ALIVE|NUM_PARALLEL|KV_CACHE_TYPE|MAX_LOADED_MODELS):[^ ]*' \
     | sort -u; then
  echo "  WARNING: could not read the startup banner from journalctl."
  echo "  Confirm manually before trusting any benchmark:  journalctl -u ollama | head -40"
fi
echo
echo "  ^ FLASH_ATTENTION must be true and CONTEXT_LENGTH 32768. If they are not,"
echo "    the override did not take and every number you measure next is invalid."
echo

# 3. Pull models from config/models.txt.
grep -vE '^\s*#|^\s*$' "$ROOT/config/models.txt" | while read -r m; do
  echo "Pulling $m ..."
  ollama pull "$m"
done

# 4. Smoke test (uses .env if present).
python3 "$ROOT/scripts/smoke-test.py"
echo "Done. Endpoint live on the LAN at http://$(hostname -I | awk '{print $1}'):11434/v1"
echo "On your main rig, set OLLAMA_HOST to that address in .env."
