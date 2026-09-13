#!/usr/bin/env python3
"""Endpoint-down alert (WP-E): fire once when the endpoint hasn't served for N minutes.

Run every minute by ops/systemd/aiserver-endpoint-watch.timer.

    python scripts/endpoint_watch.py [--minutes N] [--generate] [--state FILE]

"Serving" is the portable contract answering, not "the runner process exists": GET /v1/models,
plus with --generate a one-token completion on INFERENCE_MODEL. --generate is off in the timer
on purpose -- on a 24GB card it would reload that model every minute and evict whatever else
is resident.

One ALERT per outage, one RECOVERED when it ends. Both go to stderr with a journald priority
prefix (<2> crit, <5> notice), so `journalctl -p crit -u aiserver-endpoint-watch` finds alerts,
and to ENDPOINT_ALERT_WEBHOOK as a JSON POST when that is set (LAN/tailnet URLs only).
Exit status: 0 serving, 1 not serving.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, LLMError, load_config  # noqa: E402

DEFAULT_STATE = Path.home() / ".local" / "state" / "ai-server" / "endpoint-watch.json"


def check(llm: LLM, generate: bool) -> tuple[bool, str]:
    try:
        up = llm.ping()
    except OSError as e:  # a timeout is not a URLError
        up, why = False, str(e)
    else:
        why = "GET /models did not answer 200"
    if not up:
        return False, why
    if generate:
        try:
            llm.chat([{"role": "user", "content": "Reply with OK."}], temperature=0, max_tokens=1)
        except LLMError as e:
            if "neither content nor tool_calls" not in str(e):  # thinking model: served, no content
                return False, f"one-token completion failed: {e}"
    return True, "serving"


def step(state: dict, ok: bool, detail: str, now: float, minutes: float) -> tuple[dict, str | None]:
    """Pure state machine -> (new state, event). event is None, "ALERT" or "RECOVERED"."""
    if ok:
        return {"down_since": None, "alerted": False, "detail": detail}, ("RECOVERED" if state.get("alerted") else None)
    down_since = state.get("down_since")
    if down_since is None:  # not `or`: a timestamp of 0 is a real value
        down_since = now
    alerted = bool(state.get("alerted"))
    event = None
    if not alerted and now - down_since >= minutes * 60:
        alerted, event = True, "ALERT"
    return {"down_since": down_since, "alerted": alerted, "detail": detail}, event


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def notify(webhook: str, payload: dict) -> None:
    if not webhook:
        return
    req = urllib.request.Request(
        webhook, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except OSError as e:
        print(f"<4>WARN: alert webhook failed: {e}", file=sys.stderr)


def main(argv: list[str] | None = None, *, now: float | None = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--minutes", type=float, default=cfg.endpoint_alert_minutes)
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = ap.parse_args(argv)

    now = time.time() if now is None else now
    ok, detail = check(LLM(cfg, timeout=20, retries=0), args.generate)
    state, event = step(load_state(args.state), ok, detail, now, args.minutes)
    save_state(args.state, state)

    if event == "ALERT":
        down_for = (now - state["down_since"]) / 60
        print(f"<2>ALERT: {cfg.base_url} not serving for {down_for:.1f} min: {detail}", file=sys.stderr)
        notify(cfg.endpoint_alert_webhook, {"event": "ALERT", "endpoint": cfg.base_url, "detail": detail,
                                            "down_since": state["down_since"]})
    elif event == "RECOVERED":
        print(f"<5>RECOVERED: {cfg.base_url} serving again", file=sys.stderr)
        notify(cfg.endpoint_alert_webhook, {"event": "RECOVERED", "endpoint": cfg.base_url})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
