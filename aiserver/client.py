"""OpenAI-compatible client for the local endpoint (chat + embeddings).

Talks only to the HTTP API (/v1/chat/completions, /v1/embeddings, /api/tags) so it is
runtime-agnostic: Ollama now, llama.cpp/vLLM later, with no code change.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import Config, load_config


class LLMError(RuntimeError):
    """Endpoint unreachable, or an unexpected response shape."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    parse_error: str | None = None


@dataclass(frozen=True)
class ChatMessage:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLM:
    def __init__(
        self,
        config: Config | None = None,
        *,
        timeout: float = 300.0,
        retries: int = 2,
        backoff: float = 1.5,
        api_key: str | None = None,
    ):
        self.cfg = config or load_config()
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.api_key = api_key  # optional, for a Caddy/api-key gateway (WP-E)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    _RETRYABLE_CODES = {408, 429}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.cfg.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=self._headers())
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    try:
                        return json.load(r)
                    except ValueError as e:
                        raise LLMError(f"{url} returned HTTP 200 with a non-JSON body: {e}") from e
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code not in self._RETRYABLE_CODES and e.code < 500:
                    raise LLMError(f"{url} returned HTTP {e.code}: {body}") from e
                last = LLMError(f"HTTP {e.code}: {body}")
                if attempt < self.retries:
                    time.sleep(self.backoff ** attempt)
            except urllib.error.URLError as e:
                last = e
                if attempt < self.retries:
                    time.sleep(self.backoff ** attempt)
        if isinstance(last, LLMError):
            raise LLMError(f"{url} failed after {self.retries + 1} attempts: {last}") from last
        raise LLMError(
            f"Could not reach {url}: {last}. Is the endpoint up "
            f"(OLLAMA_HOST={self.cfg.ollama_host})?"
        )

    def chat_message(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
        **opts: Any,
    ) -> ChatMessage:
        payload = {
            "model": model or self.cfg.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            **opts,
        }
        if tools is not None:
            payload["tools"] = tools
        data = self._post("/v1/chat/completions", payload)
        try:
            raw = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected chat response shape: {e}") from e
        content = raw.get("content")
        tool_calls = [
            self._normalize_tool_call(i, tc) for i, tc in enumerate(raw.get("tool_calls") or [])
        ]
        if not (content and content.strip()) and not tool_calls:
            raise LLMError(
                "Model returned neither content nor tool_calls (empty response) -- "
                "known Ollama failure mode with tool_choice + a large system prompt"
            )
        return ChatMessage(content=content, tool_calls=tool_calls)

    @staticmethod
    def _normalize_tool_call(index: int, raw: dict[str, Any]) -> ToolCall:
        """Absorb Ollama/OpenAI wire differences: id is frequently missing, and
        `arguments` comes back as either a JSON string or an already-parsed dict
        depending on model/backend. A malformed `arguments` is recorded on
        `parse_error`, never raised -- that's the harness loop's call to make
        (recoverable model mistake, not a transport failure)."""
        call_id = raw.get("id") or f"call_{index}"
        fn = raw.get("function") or {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments", {})
        if isinstance(raw_args, dict):
            return ToolCall(id=call_id, name=name, arguments=raw_args)
        if isinstance(raw_args, str):
            if not raw_args.strip():
                return ToolCall(id=call_id, name=name, arguments={})
            try:
                parsed = json.loads(raw_args)
            except json.JSONDecodeError as e:
                return ToolCall(id=call_id, name=name, arguments={}, parse_error=f"arguments is not valid JSON: {e}")
            if isinstance(parsed, dict):
                return ToolCall(id=call_id, name=name, arguments=parsed)
            return ToolCall(
                id=call_id, name=name, arguments={},
                parse_error=f"arguments parsed to {type(parsed).__name__}, expected an object",
            )
        return ToolCall(
            id=call_id, name=name, arguments={},
            parse_error=f"arguments has unsupported type {type(raw_args).__name__}",
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        **opts: Any,
    ) -> str:
        return (self.chat_message(messages, model=model, temperature=temperature, **opts).content or "").strip()

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        payload = {"model": model or self.cfg.embed_model, "input": texts}
        data = self._post("/v1/embeddings", payload)
        try:
            # The OpenAI-compatible shape doesn't guarantee response order matches
            # input order; each item's `index` is the authoritative position.
            ordered = sorted(data["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in ordered]
        except (KeyError, TypeError) as e:
            raise LLMError(f"Unexpected embeddings response shape: {e}") from e

    def ping(self) -> bool:
        """True if the endpoint answers GET /api/tags."""
        try:
            req = urllib.request.Request(f"{self.cfg.base_url}/api/tags", headers=self._headers())
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status == 200
        except urllib.error.URLError:
            return False
