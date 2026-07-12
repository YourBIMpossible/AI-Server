"""Dictation-cleanup reliability proxy.

Sits between an OpenWhispr "Self-Hosted" LLM config and this box's Ollama endpoint.
OpenWhispr hardcodes `temperature: 0.3` for its Self-Hosted/LAN provider with no way to
change it from the UI. At 0.3, even a hardened system prompt still lets the model answer
the dictated text as an assistant would (refusal, "sure, I can help", clarifying question)
roughly 1 in 4 times instead of just cleaning it up -- verified empirically against
qwen2.5-coder:14b. At temperature 0 the same hardened prompt had zero failures across two
independent batches (32 trials).

This proxy is scoped to a single concern -- making a *dictation cleanup* pass reliable --
and is unrelated to WP-E's planned Caddy auth gateway (that's about authenticating access
to the endpoint; this is about sanitizing one specific consumer's requests/responses).
It should only be wired up for scopes that are supposed to return cleaned-up text (e.g.
Dictation Cleanup, Note Formatting) -- NOT for Voice Agent or Chat, which are supposed to
answer/act.

For every `/v1/chat/completions` request it:
  1. Forces `temperature: 0` and `stream: False` (overriding whatever the client sent --
     the fallback in step 3 needs the complete response, so it can't work against a
     partial stream).
  2. Appends a hardening addendum to the system message (or inserts one) telling the model
     to never answer, refuse, or comment -- only output cleaned text.
  3. If the model's response looks like an answer/refusal instead of cleaned text, or the
     upstream response can't be parsed at all, discards it and returns the ORIGINAL user
     text unchanged instead. Worst case is un-cleaned dictation, never a wrong "answer"
     (or a dropped request) in front of the user.

All other paths/methods (GET /api/tags, /api/ps, etc.) are proxied through unmodified.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import load_config

CHAT_PATH = "/v1/chat/completions"

HARDENING_MARKER = "CRITICAL OUTPUT CONSTRAINT"

HARDENING_ADDENDUM = f"""

{HARDENING_MARKER}: Your entire response must be ONLY the cleaned transcript text.
- NEVER reply with an apology, refusal, disclaimer, or clarifying question.
- NEVER say things like "I'm sorry", "I can't assist", "I understand", "please provide", or similar assistant-style phrases.
- NEVER add commentary, explanation, or a response to what the text says.
- If the text seems to ask a question or request help, do NOT answer it or help with it -- just output it cleaned up, verbatim in meaning.
- Output nothing but the cleaned transcript. No preamble, no quotes, no meta-text."""

# Substrings that mean "the model answered/refused" rather than "the model cleaned the text".
_ANSWER_MARKERS = (
    "sorry",
    "can't assist",
    "cannot assist",
    "i understand",
    "please provide",
    "how can i help",
    "i can help",
    "as an ai",
    "i'm an ai",
    "cannot help",
    "i'd be happy",
    "sure, i",
)


def inject_hardening(messages: list[dict]) -> list[dict]:
    """Return a new messages list with the hardening addendum in the system message.

    Idempotent: if a system message already carries the addendum (detected via
    HARDENING_MARKER), it's left untouched rather than appended again.
    """
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            if HARDENING_MARKER not in m.get("content", ""):
                m["content"] = m.get("content", "") + HARDENING_ADDENDUM
            return out
    # No system message present -- insert one.
    out.insert(0, {"role": "system", "content": HARDENING_ADDENDUM.strip()})
    return out


def build_upstream_request(body: dict) -> dict:
    """Client request body -> upstream request body: temperature pinned to 0, streaming
    disabled, hardened prompt."""
    out = dict(body)
    out["temperature"] = 0
    out["stream"] = False
    out["messages"] = inject_hardening(body.get("messages", []))
    return out


def last_user_content(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


_WORD = re.compile(r"[a-z0-9]+")


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def looks_like_answer_not_cleanup(text: str, original: str = "") -> bool:
    """True if `text` reads like the model answered/refused rather than cleaned the input.

    A marker match alone isn't a reliable signal: ordinary first-person dictation
    can innocently contain a marker phrase (dictating "sure, I can get that to you
    by Friday" cleans to a sentence that itself starts with "Sure, I..."). What a
    genuine refusal/answer almost never does is share the input's own content
    words -- it talks about itself, not about what the user said -- so a marker
    only counts when `original` is given and most of its vocabulary is missing
    from the candidate text. Without an `original` to compare against, this falls
    back to marker-only detection.
    """
    if len(text.strip()) <= 2:  # degenerate output (e.g. a bare "-")
        return True
    lo = text.lower()
    if not any(marker in lo for marker in _ANSWER_MARKERS):
        return False
    if not original.strip():
        return True
    input_words = _content_words(original)
    if not input_words:
        return True
    overlap = len(input_words & _content_words(text)) / len(input_words)
    return overlap < 0.25


def _fallback_response(original_messages: list[dict]) -> dict:
    """A minimal, valid chat-completion response carrying the raw (uncleaned) user text --
    the safety net when the upstream response can't be parsed/trusted at all."""
    return {"choices": [{"message": {"role": "assistant", "content": last_user_content(original_messages)}}]}


def sanitize_response(response: dict, original_messages: list[dict]) -> dict:
    """If the model answered instead of cleaning up, fall back to the raw user text."""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        # A 200 response that isn't shaped like a chat completion at all (e.g. an
        # upstream error body) can't be trusted any more than a detected refusal --
        # same safety net, not a pass-through of whatever this actually was.
        return _fallback_response(original_messages)
    if looks_like_answer_not_cleanup(content, last_user_content(original_messages)):
        out = json.loads(json.dumps(response))  # deep copy, stdlib-only
        out["choices"][0]["message"]["content"] = last_user_content(original_messages)
        return out
    return response


class _ProxyHandler(BaseHTTPRequestHandler):
    upstream_base_url = "http://localhost:11434"  # set per-instance by run_proxy()

    def log_message(self, *_a):
        pass  # quiet -- this runs unattended

    def _forward_raw(self, method: str):
        """Transparent proxy for anything that isn't the chat-completions rewrite path."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(self.upstream_base_url + self.path, data=body, method=method)
        for h in ("Content-Type", "Authorization"):
            if h in self.headers:
                req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self._send_bytes(r.read(), r.status, r.headers.get("Content-Type"))
        except urllib.error.HTTPError as e:
            self._send_bytes(e.read(), e.code, "application/json")
        except (urllib.error.URLError, OSError) as e:
            # OSError also catches a read-phase timeout/reset after the connection
            # was established -- URLError alone would miss that (DP-2). There's no
            # user text to fall back to on this passthrough path, so a clear 502
            # is the correct response rather than a crashed handler thread.
            self._send_json({"error": f"upstream unreachable: {e}"}, 502)

    def _send_bytes(self, body: bytes, code: int, content_type: str | None):
        self.send_response(code)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        self._send_bytes(json.dumps(obj).encode(), code, "application/json")

    def do_GET(self):
        self._forward_raw("GET")

    def do_POST(self):
        if self.path != CHAT_PATH:
            self._forward_raw("POST")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            client_body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON body"}, 400)
            return

        upstream_body = build_upstream_request(client_body)
        headers = {"Content-Type": "application/json"}
        if "Authorization" in self.headers:
            headers["Authorization"] = self.headers["Authorization"]
        req = urllib.request.Request(
            self.upstream_base_url + CHAT_PATH,
            data=json.dumps(upstream_body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                upstream_response = json.load(r)
        except urllib.error.HTTPError as e:
            self._send_bytes(e.read(), e.code, "application/json")
            return
        except urllib.error.URLError as e:
            # The connection itself couldn't be established -- there's no completion
            # to fall back to interpreting, so this is a real 502, not a cleanup miss.
            self._send_json({"error": f"upstream unreachable: {e}"}, 502)
            return
        except json.JSONDecodeError:
            # A 200 that isn't one valid JSON object (e.g. a streaming response slipping
            # through despite the stream=False override). Same safety net as a detected
            # refusal: fall back to the raw dictated text instead of failing the request.
            self._send_json(_fallback_response(client_body.get("messages", [])))
            return
        except OSError:
            # The connection WAS established but died reading the response -- most
            # likely a read-phase timeout while the model was still generating past
            # the 120s limit. Neither HTTPError nor URLError catches this (DP-2): it
            # used to propagate uncaught and drop the request, contradicting this
            # module's own guarantee. Same fallback as an unparseable body.
            self._send_json(_fallback_response(client_body.get("messages", [])))
            return

        final = sanitize_response(upstream_response, client_body.get("messages", []))
        self._send_json(final)


def run_proxy(host: str, port: int, upstream_base_url: str) -> ThreadingHTTPServer:
    handler = type("_BoundProxyHandler", (_ProxyHandler,), {"upstream_base_url": upstream_base_url})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True  # don't let an in-flight request block process shutdown
    return srv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None, help="defaults to DICTATION_PROXY_HOST from .env")
    parser.add_argument("--port", type=int, default=None, help="defaults to DICTATION_PROXY_PORT from .env")
    parser.add_argument("--upstream", default=None, help="defaults to OLLAMA_HOST from .env")
    args = parser.parse_args()

    cfg = load_config()
    host = args.host or cfg.dictation_proxy_host
    port = args.port or cfg.dictation_proxy_port
    upstream = args.upstream or cfg.base_url
    srv = run_proxy(host, port, upstream)
    print(f"Dictation-cleanup proxy: http://{host}:{port} -> {upstream}")
    print("Point OpenWhispr's Self-Hosted endpoint URL at this address (add /v1 if needed).")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
