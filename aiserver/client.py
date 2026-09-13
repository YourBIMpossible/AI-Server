"""OpenAI-compatible client for the local endpoint (chat + embeddings).

Talks only to the OpenAI-compatible surface -- chat/completions, embeddings, models --
relative to the configured base URL. Nothing here is Ollama-specific, so the runner
behind the endpoint is a replaceable implementation detail: Ollama, llama.cpp or vLLM,
with no code change. Keep it that way; runner-native paths belong in ops tooling, not
here.
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


class PromptTooLargeError(LLMError):
    """The estimated prompt exceeds the configured context window. Raised BEFORE
    sending, because some runners silently truncate an oversized prompt and answer
    anyway (Ollama 0.34.0 cuts to ~16k and returns HTTP 200) -- a wrong answer with
    no error is worse than a refusal. See decisions/2026-09-13__wp-h-runner-bakeoff.md."""


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
        max_input_tokens: int | None = None,
    ):
        self.cfg = config or load_config()
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        # Prompt-size guard budget (tokens). Falls back to config; 0 disables it.
        self.max_input_tokens = (
            max_input_tokens if max_input_tokens is not None else self.cfg.inference_max_input_tokens
        )
        # Optional, for an api-key gateway in front of the endpoint (WP-E).
        self.api_key = api_key if api_key is not None else (self.cfg.inference_api_key or None)

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
            f"(INFERENCE_BASE_URL={self.cfg.inference_base_url})?"
        )

    @staticmethod
    def estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
        """Deliberately conservative (over-)estimate of prompt tokens, with no tokenizer
        dependency and no runner-native call -- the guard must stay portable. ~3.5 chars per
        token (below the ~4 English average, so mixed code/JSON is not under-counted) plus a
        small per-message role/framing overhead. The goal is to refuse before a runner
        silently truncates, not to reproduce the server's exact count."""
        import math

        chars = 0
        for m in messages:
            c = m.get("content")
            if isinstance(c, str):
                chars += len(c)
            elif isinstance(c, list):  # OpenAI content parts
                chars += sum(len(part.get("text", "")) for part in c if isinstance(part, dict))
        return math.ceil(chars / 3.5) + 8 * len(messages)

    def _guard_prompt_size(self, messages: list[dict[str, Any]]) -> None:
        budget = self.max_input_tokens
        if not budget or budget <= 0:
            return
        est = self.estimate_prompt_tokens(messages)
        if est > budget:
            raise PromptTooLargeError(
                f"estimated prompt ~{est} tokens exceeds the {budget}-token context budget "
                f"(INFERENCE_MAX_INPUT_TOKENS). Refusing to send: the runner may silently "
                f"truncate it. Shorten the prompt, or raise the budget if the server context is larger."
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
        self._guard_prompt_size(messages)
        payload = {
            "model": model or self.cfg.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            **opts,
        }
        if tools is not None:
            payload["tools"] = tools
        data = self._post("/chat/completions", payload)
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

    def chat_timed(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        **opts: Any,
    ) -> dict[str, Any]:
        """Streamed chat with client-side timings, for benchmarks (WP-H).

        Returns content and reasoning text, `ttft_s` (first token of any kind), `ttfc_s`
        (first content token), `total_s`, `usage` (when the server honours
        stream_options.include_usage), `chunks`, `finish_reason`, and `server_timings` -- a
        non-standard timing object some servers attach, recorded as-is or None. No retries:
        a benchmark has to see failures, not paper over them.
        """
        payload = {
            "model": model or self.cfg.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            **opts,
        }
        url = f"{self.cfg.base_url}/chat/completions"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=self._headers())
        content: list[str] = []
        reasoning: list[str] = []
        ttft = ttfc = None
        usage = server_timings = finish = None
        chunks = 0
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                for raw in r:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except ValueError as e:
                        raise LLMError(f"{url} sent a non-JSON stream chunk: {data[:200]}") from e
                    if obj.get("error"):
                        raise LLMError(f"{url} stream error: {obj['error']}")
                    chunks += 1
                    now = time.perf_counter() - t0
                    for choice in obj.get("choices") or []:
                        delta = choice.get("delta") or {}
                        r_part = delta.get("reasoning") or delta.get("reasoning_content")
                        c_part = delta.get("content")
                        if (r_part or c_part) and ttft is None:
                            ttft = now
                        if c_part:
                            ttfc = now if ttfc is None else ttfc
                            content.append(c_part)
                        if r_part:
                            reasoning.append(r_part)
                        finish = choice.get("finish_reason") or finish
                    usage = obj.get("usage") or usage
                    server_timings = obj.get("timings") or server_timings
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise LLMError(f"{url} returned HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, OSError) as e:
            raise LLMError(f"Could not reach {url}: {e}") from e
        return {
            "content": "".join(content),
            "reasoning": "".join(reasoning),
            "ttft_s": ttft,
            "ttfc_s": ttfc,
            "total_s": time.perf_counter() - t0,
            "usage": usage,
            "chunks": chunks,
            "finish_reason": finish,
            "server_timings": server_timings,
        }

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        payload = {"model": model or self.cfg.embed_model, "input": texts}
        data = self._post("/embeddings", payload)
        try:
            # The OpenAI-compatible shape doesn't guarantee response order matches
            # input order; each item's `index` is the authoritative position.
            ordered = sorted(data["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in ordered]
        except (KeyError, TypeError) as e:
            raise LLMError(f"Unexpected embeddings response shape: {e}") from e

    def ping(self) -> bool:
        """True if the endpoint answers GET /models.

        Deliberately the OpenAI-compatible path, not Ollama's /api/tags: every candidate
        runner serves this one, so a runner swap does not change liveness checking.
        """
        try:
            req = urllib.request.Request(f"{self.cfg.base_url}/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status == 200
        except urllib.error.URLError:
            return False
