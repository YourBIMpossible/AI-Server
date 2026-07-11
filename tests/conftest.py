"""Shared test fixtures: a stdlib mock of the OpenAI-compatible endpoint (no real Ollama)."""
import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class _Handler(BaseHTTPRequestHandler):
    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "mock-model"}]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        if self.path == "/v1/chat/completions":
            self._send({"choices": [{"message": {"content": "ok"}}]})
        elif self.path == "/v1/embeddings":
            self._send({"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def mock_endpoint():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


# --- Deterministic embeddings endpoint, for RAG retrieval tests (WP-B) ---
# Unlike `mock_endpoint` (fixed vector), this returns a content-dependent bag-of-words
# vector so semantically-closer texts get closer vectors and KNN is meaningful. The
# same function embeds both indexed chunks and queries, so retrieval is deterministic.

_EMBED_DIM = 128


def _bow_vector(text: str) -> list[float]:
    v = [0.0] * _EMBED_DIM
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big") % _EMBED_DIM
        v[bucket] += 1.0
    return v


class _EmbedHandler(BaseHTTPRequestHandler):
    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "mock-embed"}]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/v1/embeddings":
            texts = payload.get("input", [])
            if isinstance(texts, str):
                texts = [texts]
            self._send(
                {"data": [{"index": i, "embedding": _bow_vector(t)} for i, t in enumerate(texts)]}
            )
        elif self.path == "/v1/chat/completions":
            self._send(
                {"choices": [{"message": {"content": "SYNTHESIZED ANSWER FROM CONTEXT"}}]}
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def embed_endpoint():
    srv = HTTPServer(("127.0.0.1", 0), _EmbedHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
