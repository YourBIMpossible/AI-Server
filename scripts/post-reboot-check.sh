#!/usr/bin/env bash
# WP-E: after a reboot, prove the endpoint came back correctly -- from the server's own evidence.
# No root needed. Exit 0 only when every check passes.
#
#   bash scripts/post-reboot-check.sh
#
# Checks, in order: the runner's startup banner from THIS boot carries the serving-layer env;
# /v1/models answers; the gateway refuses a missing key on every bind it was given; the
# boot-time warm-up ran; the endpoint-watch timer is active.
set -uo pipefail
fail=0
ok()   { echo "  ok   $*"; }
bad()  { echo "  FAIL $*"; fail=1; }

echo "=== boot: $(uptime -s) (up $(awk '{print int($1/60)}' /proc/uptime) min) ==="

echo "=== runner banner (journalctl -b -u ollama) ==="
banner="$(journalctl -b -u ollama --no-pager -o cat 2>/dev/null | grep -a -m1 'server config' || true)"
if [ -z "$banner" ]; then
  bad "no startup banner in this boot's journal"
else
  for want in OLLAMA_FLASH_ATTENTION:true OLLAMA_CONTEXT_LENGTH:32768 OLLAMA_MODELS:/srv/models OLLAMA_KEEP_ALIVE:2562047h OLLAMA_NUM_PARALLEL:1; do
    grep -q "$want" <<<"$banner" && ok "$want" || bad "banner lacks $want"
  done
fi
mountpoint -q /srv/models && ok "/srv/models mounted" || bad "/srv/models not mounted"

echo "=== endpoint ==="
code="$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:11434/v1/models)"
[ "$code" = 200 ] && ok "127.0.0.1:11434 /v1/models 200" || bad "127.0.0.1:11434 /v1/models -> $code"

echo "=== gateway ==="
if systemctl is-active --quiet aiserver-gateway.service; then
  ok "aiserver-gateway active (restarts: $(systemctl show -p NRestarts --value aiserver-gateway))"
  port="$(ss -ltnH | awk '$4 ~ /:114[0-9][0-9]$/ && $4 !~ /:11434$/ {sub(/.*:/, "", $4); print $4; exit}')"
  binds="$(ss -ltnH | awk -v p=":${port:-11440}" '$4 ~ p"$" {sub(/:[0-9]+$/, "", $4); print $4}')"
  [ -n "$binds" ] || bad "gateway listening on no address"
  for b in $binds; do
    c="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://$b:${port:-11440}/v1/models")"
    [ "$c" = 401 ] && ok "$b:${port:-11440} refuses a missing key (401)" || bad "$b:${port:-11440} no-key -> $c (want 401)"
  done
else
  bad "aiserver-gateway not active"
fi

echo "=== boot warm-up ==="
if journalctl -b -u aiserver-preload --no-pager -o cat 2>/dev/null | grep -q '\[OK\] warmed'; then
  ok "$(journalctl -b -u aiserver-preload --no-pager -o cat | grep '\[OK\] warmed' | tail -1)"
else
  bad "aiserver-preload did not report a warmed model this boot (journalctl -b -u aiserver-preload)"
fi

echo "=== endpoint watch ==="
systemctl is-active --quiet aiserver-endpoint-watch.timer && ok "watch timer active" || bad "watch timer not active"
if journalctl -b -u aiserver-endpoint-watch --no-pager -o cat 2>/dev/null | grep -q 'ALERT'; then
  bad "an ALERT was logged this boot: $(journalctl -b -u aiserver-endpoint-watch --no-pager -o cat | grep ALERT | tail -1)"
else
  ok "no ALERT this boot"
fi

echo
[ "$fail" = 0 ] && echo "POST-REBOOT CHECK: PASS" || echo "POST-REBOOT CHECK: FAIL"
exit "$fail"
