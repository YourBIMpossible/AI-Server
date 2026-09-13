#!/usr/bin/env bash
# WP-E acceptance: kill the runtime, prove the ENDPOINT comes back (not just a PID), and prove
# the down-alert fires and clears. Needs root. Interrupts serving for a few minutes.
#
#   sudo bash scripts/crash-recovery-test.sh
#
# Phase A: SIGKILL the runner's main process. Measure until systemd restarts it, GET /v1/models
#          answers, and a one-token completion succeeds; check the new startup banner still
#          carries the serving-layer env.
# Phase B: stop the runner for longer than the alert window; endpoint_watch must ALERT, then
#          RECOVERED once the runner is started again. Uses its own state file.
# Writes out/ops/crash-recovery-<UTC>.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
UNIT="${RUNNER_UNIT:-ollama.service}"
URL="${RUNNER_URL:-http://127.0.0.1:11434/v1}"
MODEL="${MODEL:-qwen2.5-coder:14b}"
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

now() { date +%s.%N; }
since() { python3 -c "print(round($(now) - $1, 2))"; }
models_ok() { curl -fsS -m 3 "$URL/models" >/dev/null 2>&1; }
gen_ok() {
  curl -fsS -m 300 "$URL/chat/completions" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK.\"}],\"max_tokens\":1,\"temperature\":0}" \
    >/dev/null 2>&1
}
watch() { sudo -u "$RUN_USER" python3 "$ROOT/scripts/endpoint_watch.py" --minutes 1 --state "$STATE" 2>&1 || true; }

models_ok || { echo "endpoint not serving before the test; aborting" >&2; exit 1; }
gen_ok || { echo "model $MODEL does not answer before the test; aborting" >&2; exit 1; }

echo "=== Phase A: SIGKILL ==="
old_pid="$(systemctl show -p MainPID --value "$UNIT")"
restarts_before="$(systemctl show -p NRestarts --value "$UNIT")"
t0="$(now)"; t0_epoch="$(date +%s)"
kill -9 "$old_pid"
t_active=""; t_models=""; t_gen=""
for _ in $(seq 1 600); do
  [ -z "$t_active" ] && [ "$(systemctl is-active "$UNIT")" = active ] && \
    [ "$(systemctl show -p MainPID --value "$UNIT")" != "$old_pid" ] && t_active="$(since "$t0")"
  [ -n "$t_active" ] && [ -z "$t_models" ] && models_ok && t_models="$(since "$t0")"
  if [ -n "$t_models" ]; then
    gen_ok && { t_gen="$(since "$t0")"; break; }
  fi
  sleep 0.5
done
new_pid="$(systemctl show -p MainPID --value "$UNIT")"
restarts_after="$(systemctl show -p NRestarts --value "$UNIT")"
banner="$(journalctl -u "$UNIT" --since "@$t0_epoch" --no-pager -o cat | grep -m1 'server config' || true)"
env_ok=true
for want in OLLAMA_FLASH_ATTENTION:true OLLAMA_CONTEXT_LENGTH:32768 OLLAMA_MODELS:/srv/models OLLAMA_KEEP_ALIVE:2562047h; do
  grep -q "$want" <<<"$banner" || env_ok=false
done
echo "active after ${t_active}s · /v1/models after ${t_models}s · completion after ${t_gen}s · banner env intact: $env_ok"

echo "=== Phase B: down-alert ==="
STATE="/tmp/aiserver-crash-test-watch-$$.json"  # own state: never disturbs the real timer's
systemctl stop "$UNIT"
tb="$(now)"; t_alert=""; alert_line=""
for _ in $(seq 1 12); do
  out="$(watch)"
  if grep -q ALERT <<<"$out"; then t_alert="$(since "$tb")"; alert_line="$out"; break; fi
  sleep 15
done
systemctl start "$UNIT"
t_recovered=""; recovered_line=""
for _ in $(seq 1 60); do
  out="$(watch)"
  if grep -q RECOVERED <<<"$out"; then t_recovered="$(since "$tb")"; recovered_line="$out"; break; fi
  sleep 2
done
rm -f "$STATE"
echo "alert after ${t_alert}s of downtime · recovered at ${t_recovered}s"

mkdir -p "$ROOT/out/ops"
report="$ROOT/out/ops/crash-recovery-$(date -u +%Y%m%dT%H%M%SZ).json"
# Every value reaches Python through the environment, never by pasting it into source: the
# banner and the alert lines contain quotes, and a shell-expanded heredoc broke on them
# (SyntaxError after an otherwise passing run, 2026-09-13).
CR_UNIT="$UNIT" CR_URL="$URL" CR_MODEL="$MODEL" CR_OLD_PID="$old_pid" CR_NEW_PID="$new_pid" \
CR_RESTARTS_BEFORE="$restarts_before" CR_RESTARTS_AFTER="$restarts_after" \
CR_T_ACTIVE="$t_active" CR_T_MODELS="$t_models" CR_T_GEN="$t_gen" CR_ENV_OK="$env_ok" CR_BANNER="$banner" \
CR_T_ALERT="$t_alert" CR_T_RECOVERED="$t_recovered" CR_ALERT_LINE="$alert_line" CR_RECOVERED_LINE="$recovered_line" \
python3 - "$report" <<'EOF'
import json, os, sys
e = os.environ
num = lambda k: float(e[k]) if e.get(k) else None  # noqa: E731
json.dump({
  "unit": e["CR_UNIT"], "url": e["CR_URL"], "model": e["CR_MODEL"],
  "phase_a_sigkill": {"old_pid": e["CR_OLD_PID"], "new_pid": e["CR_NEW_PID"],
    "restarts_before": e["CR_RESTARTS_BEFORE"], "restarts_after": e["CR_RESTARTS_AFTER"],
    "active_s": num("CR_T_ACTIVE"), "models_s": num("CR_T_MODELS"), "completion_s": num("CR_T_GEN"),
    "banner_env_intact": e["CR_ENV_OK"] == "true", "banner": e["CR_BANNER"][:4000]},
  "phase_b_alert": {"alert_minutes": 1, "alert_after_s": num("CR_T_ALERT"),
    "recovered_after_s": num("CR_T_RECOVERED"),
    "alert_line": e["CR_ALERT_LINE"], "recovered_line": e["CR_RECOVERED_LINE"]},
}, open(sys.argv[1], "w"), indent=2)
EOF
chown "$RUN_USER" "$report" "$ROOT/out/ops"
echo "Wrote $report"
[ -n "$t_gen" ] && [ "$env_ok" = true ] && [ -n "$t_alert" ] && [ -n "$t_recovered" ]
