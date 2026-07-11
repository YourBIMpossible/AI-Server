"""OpenAI-compatible client for the local endpoint (chat + embeddings).

Talks only to the HTTP API (/v1/chat/completions, /v1/embeddings, /api/tags) so it is
runtime-agnostic: Ollama now, llama.cpp/vLLM later, with no code change.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from .config import Config, load_config


class LLMError(RuntimeError):
    """Endpoint unreachable, or an unexpected response shape."""


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
                    return json.load(r)
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

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        **opts: Any,
    ) -> str:
        payload = {
            "model": model or self.cfg.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            **opts,
        }
        data = self._post("/v1/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected chat response shape: {e}") from e

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
