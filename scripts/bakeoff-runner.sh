#!/usr/bin/env bash
# WP-H ops tooling: put exactly one runner on the GPU under the frozen protocol
# (eval/bakeoff/protocol.md). Runner-native calls live here, never in eval/bakeoff/run.py.
#
#   scripts/bakeoff-runner.sh ollama-unload     # unload every Ollama model; verify GPU empty
#   scripts/bakeoff-runner.sh llamacpp-start    # start llama-server on 127.0.0.1 (prints start epoch)
#   scripts/bakeoff-runner.sh llamacpp-stop
#   scripts/bakeoff-runner.sh gpu-empty         # exit 0 when GPU memory < 600 MiB
#
# Env overrides: LLAMA_BIN, CUDA_LIB, MODEL_BLOB, MODEL_NAME, LLAMA_PORT.
set -euo pipefail
LLAMA_BIN="${LLAMA_BIN:-$HOME/src/llama.cpp/build-cuda/bin/llama-server}"
CUDA_LIB="${CUDA_LIB:-$HOME/.local/cuda-wheels/nvidia/cu13/lib}"
MODEL_BLOB="${MODEL_BLOB:-/srv/models/blobs/sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a}"
MODEL_NAME="${MODEL_NAME:-qwen3-coder:30b-a3b-q4_K_M}"
LLAMA_PORT="${LLAMA_PORT:-18080}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
STATE="${XDG_RUNTIME_DIR:-/tmp}/aiserver-bakeoff"
mkdir -p "$STATE"

gpu_mib() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1; }

gpu_empty() {
  for _ in $(seq 1 120); do
    [ "$(gpu_mib)" -lt 600 ] && return 0
    sleep 0.5
  done
  echo "GPU still holds $(gpu_mib) MiB" >&2
  return 1
}

case "${1:-}" in
  ollama-unload)
    for m in $(curl -fsS "$OLLAMA_URL/api/ps" | python3 -c 'import json,sys; print(" ".join(x["name"] for x in json.load(sys.stdin)["models"]))'); do
      curl -fsS "$OLLAMA_URL/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null
    done
    for _ in $(seq 1 120); do
      [ "$(curl -fsS "$OLLAMA_URL/api/ps" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["models"]))')" = 0 ] && break
      sleep 0.5
    done
    gpu_empty && echo "ollama: no models loaded, GPU $(gpu_mib) MiB"
    ;;
  llamacpp-start)
    [ -f "$STATE/llama.pid" ] && kill -0 "$(cat "$STATE/llama.pid")" 2>/dev/null && { echo "already running" >&2; exit 1; }
    date +%s.%N > "$STATE/llama.start"
    LD_LIBRARY_PATH="$CUDA_LIB" nohup "$LLAMA_BIN" -m "$MODEL_BLOB" --alias "$MODEL_NAME" \
      --host 127.0.0.1 --port "$LLAMA_PORT" \
      -c 32768 -np 1 -ngl 99 -fa on -ctk f16 -ctv f16 --jinja \
      --top-k 20 --top-p 0.8 --repeat-penalty 1.05 --no-webui \
      > "$STATE/llama.log" 2>&1 < /dev/null &
    echo $! > "$STATE/llama.pid"
    cat "$STATE/llama.start"
    ;;
  llamacpp-stop)
    if [ -f "$STATE/llama.pid" ]; then
      kill "$(cat "$STATE/llama.pid")" 2>/dev/null || true
      for _ in $(seq 1 60); do kill -0 "$(cat "$STATE/llama.pid")" 2>/dev/null || break; sleep 0.5; done
      rm -f "$STATE/llama.pid"
    fi
    gpu_empty && echo "llama-server stopped, GPU $(gpu_mib) MiB"
    ;;
  gpu-empty) gpu_empty ;;
  *) sed -n 2,11p "$0"; exit 2 ;;
esac
