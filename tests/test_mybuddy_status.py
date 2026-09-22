"""Plan step 4: scripts/mybuddy_status.py reports plain English and degrades to unknown."""
import importlib.util
import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from aiserver import load_config

REPO = Path(__file__).resolve().parent.parent
MODEL = "test-model:q4"


def _load():
    spec = importlib.util.spec_from_file_location("mybuddy_status", REPO / "scripts" / "mybuddy_status.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def runner():
    """Mock server: path -> (status, json). Mutate `routes` per test."""
    routes = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            code, obj = routes.get(self.path, (404, {}))
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", routes
    srv.shutdown()


def _cfg(base):
    return load_config(dotenv=REPO / "no-such.env",
                       overrides={"INFERENCE_BASE_URL": base + "/v1", "INFERENCE_MODEL": MODEL})


def _all_up(monkeypatch, base, routes, loaded=(MODEL,)):
    routes["/v1/models"] = (200, {"data": []})
    routes["/api/ps"] = (200, {"models": [{"name": n} for n in loaded]})
    routes["/gw"] = (401, {})
    for p in ("/owui", "/allm", "/lc"):
        routes[p] = (200, {})
    for env, p in (("MYBUDDY_GATEWAY_URL", "/gw"), ("MYBUDDY_OPENWEBUI_URL", "/owui"),
                   ("MYBUDDY_ANYTHINGLLM_URL", "/allm"), ("MYBUDDY_LIBRECHAT_URL", "/lc")):
        monkeypatch.setenv(env, base + p)


def _states(lines):
    return {l.name: l.state for l in lines}


def test_all_online_and_loaded(runner, monkeypatch):
    base, routes = runner
    _all_up(monkeypatch, base, routes)
    s = _states(_load().collect(_cfg(base)))
    assert s == {"MyBuddy model server": "online", "MyBuddy gateway": "online",
                 "Open WebUI": "online", "AnythingLLM": "online", "LibreChat": "online",
                 "Selected model": "loaded"}


def test_model_not_loaded(runner, monkeypatch):
    base, routes = runner
    _all_up(monkeypatch, base, routes, loaded=("other:1b",))
    assert _states(_load().collect(_cfg(base)))["Selected model"] == "not loaded"


def test_runner_without_ps_says_unknown_with_reason(runner, monkeypatch):
    base, routes = runner
    _all_up(monkeypatch, base, routes)
    del routes["/api/ps"]
    line = [l for l in _load().collect(_cfg(base)) if l.name == "Selected model"][0]
    assert line.state == "unknown" and line.why


def test_everything_down_is_offline_without_tracebacks(monkeypatch, capsys):
    mod = _load()
    dead = "http://127.0.0.1:1"
    for env in ("MYBUDDY_GATEWAY_URL", "MYBUDDY_OPENWEBUI_URL", "MYBUDDY_ANYTHINGLLM_URL",
                "MYBUDDY_LIBRECHAT_URL"):
        monkeypatch.setenv(env, dead)
    lines = mod.collect(_cfg(dead))
    s = _states(lines)
    assert s["MyBuddy model server"] == "offline"
    assert s["Selected model"] == "unknown"
    text = "\n".join(l.render() for l in lines)
    assert "Traceback" not in text and "127.0.0.1" not in text
