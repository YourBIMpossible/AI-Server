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


# --- DP-1: a marker alone is not enough once there's an input to compare against ------


def test_looks_like_answer_ignores_marker_when_text_echoes_the_input():
    # Genuine dictation can innocently start with an answer-shaped phrase --
    # "um, sure I can, uh, get that to you by Friday" cleans to a sentence that
    # itself starts with "Sure, I...". It must not be treated as a refusal because
    # it shares the input's own content words, which a real refusal never does.
    original = "um, sure I can, uh, get that to you by Friday"
    cleaned = "Sure, I can get that to you by Friday."
    assert looks_like_answer_not_cleanup(cleaned, original) is False


def test_looks_like_answer_still_flags_a_real_refusal_against_the_input():
    original = "Here is a PDF for you to review."
    refusal = "I'm sorry, I can't assist with that."
    assert looks_like_answer_not_cleanup(refusal, original) is True


def test_looks_like_answer_falls_back_to_marker_only_without_an_input_to_compare():
    # No `original` given (e.g. a direct caller) preserves the old marker-only
    # contract -- this is what test_looks_like_answer_flags_known_bad_outputs and
    # test_looks_like_answer_allows_clean_text already exercise above.
    assert looks_like_answer_not_cleanup("Sure, I can help with that.") is True


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


def test_sanitize_response_preserves_cleanup_that_echoes_an_answer_shaped_phrase():
    # DP-1 integration: the marker-only version of this check used to discard
    # legitimate dictation just because it started with "Sure, I...".
    original_messages = [{"role": "user", "content": "um, sure I can, uh, get that to you by Friday"}]
    response = {"choices": [{"message": {"content": "Sure, I can get that to you by Friday."}}]}
    out = sanitize_response(response, original_messages)
    assert out["choices"][0]["message"]["content"] == "Sure, I can get that to you by Friday."


def test_sanitize_response_falls_back_when_response_has_no_recognizable_content():
    # DP-CLEAN: a 200-but-error-shaped body (e.g. {"error": "..."}) must not pass
    # through unchanged -- it's just as untrustworthy as a detected refusal.
    original_messages = [{"role": "user", "content": "Here is a PDF for you to review."}]
    response = {"error": "something went wrong upstream"}
    out = sanitize_response(response, original_messages)
    assert out["choices"][0]["message"]["content"] == "Here is a PDF for you to review."


# --- integration: a mock upstream + the real proxy server ------------------------------


class _MockUpstream(BaseHTTPRequestHandler):
    """Stands in for Ollama. Records the last request body/headers it received and
    returns whatever `_MockUpstream.next_content`/`next_status` are set to, so a
    test can script a refusal or an upstream error."""

    next_content = "cleaned text"
    next_status = 200
    last_request_body = None
    last_request_headers = None
    last_request_path = None

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
        raw = self.rfile.read(n)
        _MockUpstream.last_request_body = json.loads(raw) if raw else None
        _MockUpstream.last_request_headers = dict(self.headers)
        _MockUpstream.last_request_path = self.path
        if _MockUpstream.next_status != 200:
            body = json.dumps({"error": "mock upstream error"}).encode()
            self.send_response(_MockUpstream.next_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps(
            {"choices": [{"message": {"content": _MockUpstream.next_content}}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(autouse=True)
def _reset_mock_upstream_state():
    # Class-level scripting attrs persist across tests unless reset; guard against
    # order-dependent leakage now that next_status is mutable too (not just next_content).
    _MockUpstream.next_content = "cleaned text"
    _MockUpstream.next_status = 200
    _MockUpstream.last_request_body = None
    _MockUpstream.last_request_headers = None
    _MockUpstream.last_request_path = None
    yield


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


def test_proxy_forwards_non_chat_post_transparently(proxy):
    # DP-TESTS: only GET passthrough was covered; /api/generate-style POSTs go
    # through the same _forward_raw path and must reach the same upstream path.
    out = _post(proxy + "/api/generate", {"model": "m", "prompt": "hi"})
    assert _MockUpstream.last_request_path == "/api/generate"
    assert out["choices"][0]["message"]["content"] == "cleaned text"


def test_proxy_rejects_invalid_client_json(proxy):
    req = urllib.request.Request(
        proxy + "/v1/chat/completions", data=b"{not valid json", headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        assert False, "expected an HTTPError"
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_proxy_passes_through_upstream_http_error_on_chat_path(proxy):
    _MockUpstream.next_status = 500
    try:
        _post(
            proxy + "/v1/chat/completions",
            {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert False, "expected an HTTPError"
    except urllib.error.HTTPError as e:
        assert e.code == 500


def test_proxy_returns_502_when_upstream_is_unreachable():
    # No mock_upstream fixture here -- point straight at a closed port, mirroring
    # test_client.py's test_endpoint_down_raises pattern.
    srv = run_proxy("127.0.0.1", 0, "http://127.0.0.1:1")
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            assert False, "expected an HTTPError"
        except urllib.error.HTTPError as e:
            assert e.code == 502
    finally:
        srv.shutdown()


def test_proxy_forwards_authorization_header_on_chat_path(proxy):
    # DP-4: WP-E's planned Caddy api-key gateway sits in front of the same
    # upstream this proxy targets -- dropping the header would 401 every request.
    req = urllib.request.Request(
        proxy + "/v1/chat/completions",
        data=json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer secret-token"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass
    assert _MockUpstream.last_request_headers.get("Authorization") == "Bearer secret-token"


def test_proxy_forwards_authorization_header_on_passthrough_path(proxy):
    req = urllib.request.Request(
        proxy + "/api/tags", headers={"Authorization": "Bearer secret-token"}
    )
    with urllib.request.urlopen(req, timeout=10):
        pass
    # /api/tags is a GET in this fixture's mock, so assert via a POST passthrough instead
    req2 = urllib.request.Request(
        proxy + "/api/generate",
        data=json.dumps({"prompt": "hi"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer secret-token"},
    )
    with urllib.request.urlopen(req2, timeout=10):
        pass
    assert _MockUpstream.last_request_headers.get("Authorization") == "Bearer secret-token"


def test_proxy_falls_back_instead_of_dropping_request_on_read_timeout(proxy, mock_upstream, monkeypatch):
    # DP-2: a read-phase timeout (e.g. the model still generating past the read
    # timeout) used to raise TimeoutError, which neither HTTPError nor URLError
    # catches -- it escaped do_POST uncaught and dropped the request. Proven here
    # by injecting the exact exception on the proxy's call to its upstream,
    # rather than waiting out a real 120s timeout.
    #
    # The patch must be surgical: urllib.request is a single shared module object,
    # so a blanket patch of urlopen would also break this test's own call to the
    # proxy below (same function, same process). Only raise for requests aimed at
    # the mock upstream; let the request to the proxy itself go through for real.
    import aiserver.dictation_proxy as dp

    real_urlopen = dp.urllib.request.urlopen

    def urlopen_that_times_out_for_upstream_only(req, *a, **kw):
        if req.full_url.startswith(mock_upstream):
            raise TimeoutError("timed out")
        return real_urlopen(req, *a, **kw)

    monkeypatch.setattr(dp.urllib.request, "urlopen", urlopen_that_times_out_for_upstream_only)
    out = _post(
        proxy + "/v1/chat/completions",
        {"model": "m", "messages": [{"role": "user", "content": "Here is a PDF for you to review."}]},
    )
    assert out["choices"][0]["message"]["content"] == "Here is a PDF for you to review."


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
