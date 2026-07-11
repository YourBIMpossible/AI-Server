import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aiserver.dictation_proxy import (
    build_upstream_request,
    inject_hardening,
    last_user_content,
    looks_like_answer_not_cleanup,
    run_proxy,
    sanitize_response,
)


# --- pure functions -------------------------------------------------------------------


def test_inject_hardening_appends_to_existing_system_message():
    messages = [
        {"role": "system", "content": "You are a cleanup tool."},
        {"role": "user", "content": "hello"},
    ]
    out = inject_hardening(messages)
    assert out[0]["role"] == "system"
    assert out[0]["content"].startswith("You are a cleanup tool.")
    assert "CRITICAL OUTPUT CONSTRAINT" in out[0]["content"]
    assert messages[0]["content"] == "You are a cleanup tool."  # original untouched


def test_inject_hardening_inserts_system_message_if_absent():
    messages = [{"role": "user", "content": "hello"}]
    out = inject_hardening(messages)
    assert out[0]["role"] == "system"
    assert "CRITICAL OUTPUT CONSTRAINT" in out[0]["content"]
    assert out[1] == {"role": "user", "content": "hello"}


def test_inject_hardening_is_idempotent():
    messages = [{"role": "system", "content": "base prompt"}]
    once = inject_hardening(messages)
    twice = inject_hardening(once)
    assert once[0]["content"] == twice[0]["content"]
    assert twice[0]["content"].count("CRITICAL OUTPUT CONSTRAINT") == 1


def test_build_upstream_request_forces_temperature_zero():
    body = {"model": "qwen2.5-coder:14b", "temperature": 0.3, "messages": [{"role": "user", "content": "hi"}]}
    out = build_upstream_request(body)
    assert out["temperature"] == 0
    assert "CRITICAL OUTPUT CONSTRAINT" in out["messages"][0]["content"]


def test_build_upstream_request_forces_stream_false():
    # The sanitize/fallback safety net needs the complete response; it can't work
    # against a partial stream, so streaming must never reach the upstream.
    body = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    out = build_upstream_request(body)
    assert out["stream"] is False


def test_last_user_content_picks_most_recent_user_message():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    assert last_user_content(messages) == "second"


@pytest.mark.parametrize(
    "text",
    [
        "I'm sorry, I can't assist with that.",
        "Please provide the PDF for me to review.",
        "Sure, I can help with that.",
        "-",
        "",
    ],
)
def test_looks_like_answer_flags_known_bad_outputs(text):
    assert looks_like_answer_not_cleanup(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Here's a PDF for you to review.",
        "OpenWhispr is trying to apply what I am asking it to type.",
        "I need to fix this bug in the code.",
    ],
)
def test_looks_like_answer_allows_clean_text(text):
    assert looks_like_answer_not_cleanup(text) is False


def test_sanitize_response_replaces_refusal_with_original_user_text():
    original_messages = [{"role": "user", "content": "Here is a PDF for you to review."}]
    response = {"choices": [{"message": {"content": "I'm sorry, I can't assist with that."}}]}
    out = sanitize_response(response, original_messages)
    assert out["choices"][0]["message"]["content"] == "Here is a PDF for you to review."
    # original response dict must not be mutated
    assert response["choices"][0]["message"]["content"] == "I'm sorry, I can't assist with that."


def test_sanitize_response_passes_through_clean_content():
    original_messages = [{"role": "user", "content": "Here is a PDF for you to review."}]
    response = {"choices": [{"message": {"content": "Here's a PDF for you to review."}}]}
    out = sanitize_response(response, original_messages)
    assert out["choices"][0]["message"]["content"] == "Here's a PDF for you to review."


# --- integration: a mock upstream + the real proxy server ------------------------------


class _MockUpstream(BaseHTTPRequestHandler):
    """Stands in for Ollama. Records the last request body it received and returns
    whatever `_MockUpstream.next_content` is set to, so a test can script a refusal."""

    next_content = "cleaned text"
    last_request_body = None

    def log_message(self, *_a):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            body = json.dumps({"models": [{"name": "mock"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _MockUpstream.last_request_body = json.loads(self.rfile.read(n))
        body = json.dumps(
            {"choices": [{"message": {"content": _MockUpstream.next_content}}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def mock_upstream():
    srv = HTTPServer(("127.0.0.1", 0), _MockUpstream)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


@pytest.fixture()
def proxy(mock_upstream):
    srv = run_proxy("127.0.0.1", 0, mock_upstream)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


def _post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def test_proxy_forces_temperature_zero_upstream(proxy):
    _MockUpstream.next_content = "cleaned text"
    _post(
        proxy + "/v1/chat/completions",
        {"model": "m", "temperature": 0.3, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert _MockUpstream.last_request_body["temperature"] == 0
    assert "CRITICAL OUTPUT CONSTRAINT" in _MockUpstream.last_request_body["messages"][0]["content"]


def test_proxy_falls_back_to_raw_text_on_refusal(proxy):
    _MockUpstream.next_content = "I'm sorry, I can't assist with that."
    out = _post(
        proxy + "/v1/chat/completions",
        {"model": "m", "messages": [{"role": "user", "content": "Here is a PDF for you to review."}]},
    )
    assert out["choices"][0]["message"]["content"] == "Here is a PDF for you to review."


def test_proxy_passes_through_clean_output(proxy):
    _MockUpstream.next_content = "Here's a PDF for you to review."
    out = _post(
        proxy + "/v1/chat/completions",
        {"model": "m", "messages": [{"role": "user", "content": "Here is a PDF for you to review."}]},
    )
    assert out["choices"][0]["message"]["content"] == "Here's a PDF for you to review."


def test_proxy_transparently_forwards_get_requests(proxy):
    req = urllib.request.Request(proxy + "/api/tags")
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    assert data == {"models": [{"name": "mock"}]}


# --- malformed upstream response (e.g. streaming slipping through) --------------------


class _MalformedUpstream(BaseHTTPRequestHandler):
    """Returns a 200 whose body is NOT one valid JSON object -- what a streaming/ndjson
    response looks like. Proves the proxy falls back instead of dropping the request."""

    def log_message(self, *_a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        body = b'{"choices": [{"delta": {"content": "partial"}}]}\n{"more": "chunks"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def malformed_upstream():
    srv = HTTPServer(("127.0.0.1", 0), _MalformedUpstream)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


@pytest.fixture()
def malformed_proxy(malformed_upstream):
    srv = run_proxy("127.0.0.1", 0, malformed_upstream)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


def test_proxy_falls_back_to_raw_text_on_malformed_upstream_response(malformed_proxy):
    out = _post(
        malformed_proxy + "/v1/chat/completions",
        {"model": "m", "messages": [{"role": "user", "content": "Here is a PDF for you to review."}]},
    )
    assert out["choices"][0]["message"]["content"] == "Here is a PDF for you to review."
