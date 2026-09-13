#!/usr/bin/env bash
# WP-H: one complete bakeoff session under eval/bakeoff/protocol.md, same hardware, same session.
# No root needed. Ends with llama-server stopped and Ollama serving as before.
#
#   scripts/bakeoff-session.sh 2>&1 | tee out/bakeoff/session.log
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
# Exclusive GPU work: re-exec under the interlock (ops/PRODUCTION-CONTRACT.md). AISERVER_NOLOCK=1 skips.
if [ -z "${AISERVER_GPU_LOCKED:-}" ] && [ -z "${AISERVER_NOLOCK:-}" ]; then
  export AISERVER_GPU_LOCKED=1
  exec "$PY" "$ROOT/scripts/gpu_lock.py" run --purpose "WP-H bakeoff session" -- "$0" "$@"
fi
MODEL="qwen3-coder:30b-a3b-q4_K_M"
OLLAMA="http://127.0.0.1:11434/v1"
LLAMA="http://127.0.0.1:18080/v1"
OUT="$ROOT/out/bakeoff"
RUNNER="$ROOT/scripts/bakeoff-runner.sh"
STATE="${XDG_RUNTIME_DIR:-/tmp}/aiserver-bakeoff"
mkdir -p "$OUT"
cd "$ROOT"
say() { echo; echo "##### $* ($(date -u +%H:%M:%S))"; }
measure() { "$PY" -m eval.bakeoff.run measure --model "$MODEL" --out "$OUT" "$@"; }

# Unattended: the acceptance job is launched by a transient systemd timer, not by this shell.
scheduled_acceptance() {  # label base-url
  local unit="aiserver-acceptance-$1-$(date +%s)"
  systemd-run --user --unit="$unit" --on-active=15s --collect \
    --working-directory="$ROOT" --setenv=EVAL_JUDGE_MODEL="$MODEL" \
    "$PY" "$ROOT/scripts/automation_acceptance.py" --label "$1" --base-url "$2" --model "$MODEL" --out "$ROOT/out"
  sleep 20
  while systemctl --user is-active --quiet "$unit.service" || systemctl --user is-active --quiet "$unit.timer"; do sleep 5; done
  journalctl --user -u "$unit.service" --no-pager -o cat | tail -3
}

say "Ollama: unload everything, verify GPU empty"
"$RUNNER" ollama-unload
say "Ollama: cold x3"
for i in 1 2 3; do "$RUNNER" ollama-unload >/dev/null; measure --runner ollama --base-url "$OLLAMA" --phase cold --cycle "$i"; done
say "Ollama: warm"
measure --runner ollama --base-url "$OLLAMA" --phase warm
say "Ollama: probes"
measure --runner ollama --base-url "$OLLAMA" --phase probes
say "Ollama: real automation, scheduled"
scheduled_acceptance ollama "$OLLAMA" || true

say "Swap: Ollama unloaded, llama-server up"
"$RUNNER" ollama-unload
say "llama-server: cold x3 (process start -> /v1/models 200 -> first TTFT)"
for i in 1 2 3; do
  "$RUNNER" llamacpp-stop >/dev/null 2>&1 || true
  start="$("$RUNNER" llamacpp-start)"
  measure --runner llamacpp --base-url "$LLAMA" --phase cold --cycle "$i" --ready-since "$start"
done
grep -E "offloaded|flash_attn|n_ctx|type_k" "$STATE/llama.log" | head -6 || true
say "llama-server: warm"
measure --runner llamacpp --base-url "$LLAMA" --phase warm
say "llama-server: probes"
measure --runner llamacpp --base-url "$LLAMA" --phase probes
say "llama-server: full WP-F (semantic, self-judged on the same artifact)"
INFERENCE_BASE_URL="$LLAMA" INFERENCE_MODEL="$MODEL" EVAL_JUDGE_MODEL="$MODEL" OUT="$OUT/wpf-llamacpp" "$PY" -m eval.run || true
say "llama-server: real automation, scheduled"
scheduled_acceptance llamacpp "$LLAMA" || true
cp "$STATE/llama.log" "$OUT/llama-server.log" 2>/dev/null || true
"$RUNNER" llamacpp-stop

say "Ollama: full WP-F on the same artifact, self-judged (incumbent comparison)"
INFERENCE_BASE_URL="$OLLAMA" INFERENCE_MODEL="$MODEL" EVAL_JUDGE_MODEL="$MODEL" OUT="$OUT/wpf-ollama" "$PY" -m eval.run || true

say "Report"
"$PY" -m eval.bakeoff.run report "$OUT"/ollama-*.jsonl "$OUT"/llamacpp-*.jsonl --out "$OUT" \
  --header "Artifact sha256-1194192c… (${MODEL}), hardware profile mybuddy-3090-02, protocol eval/bakeoff/protocol.md"
say "BAKEOFF SESSION DONE"
