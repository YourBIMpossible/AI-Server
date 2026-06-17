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

# 2. Expose on the LAN so the main rig can reach it (default binds to 127.0.0.1 only).
echo "Configuring Ollama to listen on the LAN (0.0.0.0:11434)..."
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama || true

# 3. Pull models from config/models.txt.
grep -vE '^\s*#|^\s*$' "$ROOT/config/models.txt" | while read -r m; do
  echo "Pulling $m ..."
  ollama pull "$m"
done

# 4. Smoke test (uses .env if present).
python3 "$ROOT/scripts/smoke-test.py"
echo "Done. Endpoint live on the LAN at http://$(hostname -I | awk '{print $1}'):11434/v1"
echo "On your main rig, set OLLAMA_HOST to that address in .env."
