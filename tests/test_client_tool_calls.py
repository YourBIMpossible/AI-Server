"""aiserver.client.LLM.chat_message(): normalized tool_calls, thin chat() wrapper."""
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aiserver import LLMError
from aiserver.client import LLM
from aiserver.config import load_config
from conftest import _running, _sequenced_server


def _cfg(tmp_path, host):
    return load_config(dotenv=tmp_path / "none.env", overrides={"OLLAMA_HOST": host})


def test_chat_message_returns_final_content_with_no_tool_calls(tmp_path):
    srv, handler = _sequenced_server(
        [(200, {"choices": [{"message": {"role": "assistant", "content": "hi there"}}]})]
    )
    with _running(srv) as url:
        msg = LLM(_cfg(tmp_path, url)).chat_message([{"role": "user", "content": "hi"}])
    assert msg.content == "hi there"
    assert msg.tool_calls == []


def test_chat_message_normalizes_missing_id_and_string_arguments(tmp_path):
    body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "knowledge", "arguments": '{"question": "why?"}'}}
                ],
            }
        }]
    }
    srv, handler = _sequenced_server([(200, body)])
    with _running(srv) as url:
        msg = LLM(_cfg(tmp_path, url)).chat_message([{"role": "user", "content": "hi"}])
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.id  # synthesized, since the wire response omitted it
    assert tc.name == "knowledge"
    assert tc.arguments == {"question": "why?"}
    assert tc.parse_error is None


def test_chat_message_normalizes_dict_arguments(tmp_path):
    body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_9", "type": "function",
                     "function": {"name": "knowledge", "arguments": {"question": "already a dict"}}}
                ],
            }
        }]
    }
    srv, handler = _sequenced_server([(200, body)])
    with _running(srv) as url:
        msg = LLM(_cfg(tmp_path, url)).chat_message([{"role": "user", "content": "hi"}])
    tc = msg.tool_calls[0]
    assert tc.id == "call_9"
    assert tc.arguments == {"question": "already a dict"}


def test_chat_message_flags_unparseable_arguments_without_raising(tmp_path):
    body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "knowledge", "arguments": "{not valid json"}}
                ],
            }
        }]
    }
    srv, handler = _sequenced_server([(200, body)])
    with _running(srv) as url:
        msg = LLM(_cfg(tmp_path, url)).chat_message([{"role": "user", "content": "hi"}])
    tc = msg.tool_calls[0]
    assert tc.parse_error is not None
    assert tc.arguments == {}


def test_chat_message_raises_on_empty_content_and_no_tool_calls(tmp_path):
    srv, handler = _sequenced_server([(200, {"choices": [{"message": {"role": "assistant", "content": ""}}]})])
    with _running(srv) as url:
        with pytest.raises(LLMError):
            LLM(_cfg(tmp_path, url)).chat_message([{"role": "user", "content": "hi"}])


def test_chat_still_returns_plain_string_for_existing_callers(tmp_path):
    srv, handler = _sequenced_server([(200, {"choices": [{"message": {"content": "  ok  "}}]})])
    with _running(srv) as url:
        assert LLM(_cfg(tmp_path, url)).chat([{"role": "user", "content": "hi"}]) == "ok"


def test_chat_message_sends_tools_payload_when_provided(tmp_path):
    captured = {}

    class _CapturingHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            import json as _json
            captured["body"] = _json.loads(self.rfile.read(n))
            resp = _json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _CapturingHandler)
    with _running(srv) as url:
        tools = [{"type": "function", "function": {"name": "knowledge", "parameters": {}}}]
        LLM(_cfg(tmp_path, url)).chat_message([{"role": "user", "content": "hi"}], tools=tools)
    assert captured["body"]["tools"] == tools
