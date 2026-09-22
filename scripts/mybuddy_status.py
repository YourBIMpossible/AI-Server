#!/usr/bin/env python3
"""Plain-English MyBuddy readiness check (plan step 4). Run on the box:  mybuddy-status

Prints one line per part: model server, gateway, the three UIs, and whether the selected
model is loaded. A check that cannot run says `unknown` and why, in one sentence. No stack
traces, addresses or subnets in the output. Exit 0 when everything is online and the model
is loaded, 1 otherwise.

The model server is probed through the OpenAI-compatible `/v1/models`. "Loaded" uses the
runner-native `/api/ps` (allowed in ops tooling) and degrades to `unknown` when the runner
doesn't offer it. Ports are overridable with MYBUDDY_GATEWAY_URL / MYBUDDY_*_URL.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import load_config

TIMEOUT = 4.0

# name -> (env override, default URL). Loopback: the UIs bind 127.0.0.1 on the box.
_SERVICES = {
    "MyBuddy gateway": ("MYBUDDY_GATEWAY_URL", "http://127.0.0.1:11440/v1/models"),
    "Open WebUI": ("MYBUDDY_OPENWEBUI_URL", "http://127.0.0.1:3000/"),
    "AnythingLLM": ("MYBUDDY_ANYTHINGLLM_URL", "http://127.0.0.1:3001/"),
    "LibreChat": ("MYBUDDY_LIBRECHAT_URL", "http://127.0.0.1:3080/"),
}


@dataclass
class Line:
    name: str
    state: str
    why: str = ""

    def render(self) -> str:
        return f"{self.name}: {self.state}" + (f" ({self.why})" if self.why else "")


def _get(url: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    """HTTP status and body. An HTTP error status is an answer, not a failure."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def _probe(name: str, url: str, ok_codes: tuple[int, ...]) -> Line:
    try:
        code, _ = _get(url)
    except (urllib.error.URLError, OSError, ValueError):
        return Line(name, "offline")
    if code in ok_codes:
        return Line(name, "online")
    return Line(name, "offline", f"it answered with an unexpected status {code}")


def _runner_root(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base[: -len("/v1")] if base.endswith("/v1") else base


def check_model_server(base_url: str, key: str) -> Line:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        code, _ = _get(base_url.rstrip("/") + "/models", headers)
    except (urllib.error.URLError, OSError, ValueError):
        return Line("MyBuddy model server", "offline")
    if code == 200:
        return Line("MyBuddy model server", "online")
    return Line("MyBuddy model server", "offline", f"it answered with status {code}")


def check_loaded(base_url: str, model: str, server_online: bool) -> Line:
    name = "Selected model"
    if not server_online:
        return Line(name, "unknown", "the model server is offline, so it can't be asked")
    try:
        code, body = _get(_runner_root(base_url) + "/api/ps")
    except (urllib.error.URLError, OSError, ValueError):
        return Line(name, "unknown", "the model server didn't answer the loaded-models question")
    if code != 200:
        return Line(name, "unknown", "this model server doesn't report which models are loaded")
    try:
        loaded = {m.get("name") or m.get("model") for m in json.loads(body).get("models", [])}
    except (ValueError, AttributeError):
        return Line(name, "unknown", "the loaded-models answer couldn't be read")
    return Line(name, "loaded" if model in loaded else "not loaded", model)


def collect(cfg) -> list[Line]:
    server = check_model_server(cfg.base_url, cfg.inference_api_key)
    lines = [server]
    for name, (env, default) in _SERVICES.items():
        url = os.environ.get(env) or default
        # the gateway refusing a keyless request (401) still proves it is up and guarding
        ok = (200, 401) if name == "MyBuddy gateway" else (200,)
        lines.append(_probe(name, url, ok))
    lines.append(check_loaded(cfg.base_url, cfg.model, server.state == "online"))
    return lines


def main() -> int:
    try:
        cfg = load_config()
    except (OSError, ValueError):
        print("MyBuddy status: unknown (the AI-Server settings file couldn't be read)")
        return 1
    lines = collect(cfg)
    for line in lines:
        print(line.render())
    ready = all(l.state in ("online", "loaded") for l in lines)
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
