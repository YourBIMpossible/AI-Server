import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aiserver.client import LLM, LLMError
from aiserver.config import load_config


def _cfg(tmp_path, host):
    return load_config(dotenv=tmp_path / "none.env", overrides={"OLLAMA_HOST": host})


def test_chat_and_embed(mock_endpoint, tmp_path):
    llm = LLM(_cfg(tmp_path, mock_endpoint))
    assert llm.ping() is True
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    vecs = llm.embed(["a", "b"])
    assert vecs and isinstance(vecs[0], list) and len(vecs[0]) == 3


def test_endpoint_down_raises(tmp_path):
    llm = LLM(_cfg(tmp_path, "http://127.0.0.1:1"), retries=0, timeout=1)
    assert llm.ping() is False
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


# --- CLIENT-1: HTTPError must not be swallowed by the URLError branch -----


def _sequenced_server(responses):
    """responses: list of (status_code, json_body); last entry repeats once exhausted."""

    class Handler(BaseHTTPRequestHandler):
        calls = 0

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            idx = min(Handler.calls, len(responses) - 1)
            Handler.calls += 1
            code, obj = responses[idx]
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    return HTTPServer(("127.0.0.1", 0), Handler), Handler


@contextmanager
def _running(srv):
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


def test_4xx_is_not_retried_and_surfaces_server_body(tmp_path):
    srv, handler = _sequenced_server([(400, {"error": "model 'x' not found"})])
    with _running(srv) as url:
        llm = LLM(_cfg(tmp_path, url), retries=2)
        with pytest.raises(LLMError) as exc:
            llm.chat([{"role": "user", "content": "hi"}])
    assert "400" in str(exc.value)
    assert "model 'x' not found" in str(exc.value)
    assert handler.calls == 1  # non-retryable 4xx must not be retried


def test_5xx_is_retried_and_can_recover(tmp_path):
    srv, handler = _sequenced_server(
        [
            (500, {"error": "temporary"}),
            (500, {"error": "temporary"}),
            (200, {"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    with _running(srv) as url:
        llm = LLM(_cfg(tmp_path, url), retries=2, backoff=0.01)
        assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert handler.calls == 3


def test_5xx_exhausted_retries_reports_status_not_endpoint_down(tmp_path):
    srv, handler = _sequenced_server([(503, {"error": "overloaded"})])
    with _running(srv) as url:
        llm = LLM(_cfg(tmp_path, url), retries=1, backoff=0.01)
        with pytest.raises(LLMError) as exc:
            llm.chat([{"role": "user", "content": "hi"}])
    assert "503" in str(exc.value)
    assert handler.calls == 2


# --- RAG-1: embeddings must be reordered by index, not trusted positionally -


def _fixed_body_server(obj):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    return HTTPServer(("127.0.0.1", 0), Handler)


def test_embed_reorders_by_index_when_response_is_scrambled(tmp_path):
    srv = _fixed_body_server(
        {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}
    )
    with _running(srv) as url:
        vecs = LLM(_cfg(tmp_path, url)).embed(["a", "b"])
    assert vecs == [[1.0], [2.0]]


def test_embed_missing_index_raises_instead_of_trusting_order(tmp_path):
    srv = _fixed_body_server({"data": [{"embedding": [1.0]}]})
    with _running(srv) as url:
        with pytest.raises(LLMError):
            LLM(_cfg(tmp_path, url)).embed(["a"])
