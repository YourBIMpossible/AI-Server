"""Configuration: load .env from the repo root, with environment overrides.

Merge order (low -> high precedence):
    built-in defaults < .env file < process environment < explicit overrides
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFAULTS = {
    "INFERENCE_BASE_URL": "http://localhost:11434/v1",
    "INFERENCE_API_KEY": "",
    "INFERENCE_MODEL": "qwen2.5-coder:14b",
    "INFERENCE_EMBED_MODEL": "nomic-embed-text",
    "WORKSPACE": r"F:\BIMpossible-Workspace",
    "OUT": "./out",
    "DIGEST_DAYS": "7",
    "EVAL_PASS_THRESHOLD": "0.8",
    "BASELINE_MODEL": "claude-opus-4-8",
    # Model that grades rubric "judge" criteria; blank = the model under test (self-judged).
    "EVAL_JUDGE_MODEL": "",
    # Endpoint-down alert (scripts/endpoint_watch.py): minutes not serving before one alert,
    # and an optional LAN/tailnet webhook that receives it as JSON.
    "ENDPOINT_ALERT_MINUTES": "3",
    "ENDPOINT_ALERT_WEBHOOK": "",
    "DICTATION_PROXY_HOST": "127.0.0.1",
    "DICTATION_PROXY_PORT": "11435",
}


def _strip_quotes(v: str) -> str:
    """Strip one layer of matching outer quotes, e.g. INFERENCE_MODEL="local-workhorse"."""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _non_empty(d: dict[str, str]) -> dict[str, str]:
    """Drop empty-string values so a blank KEY= (in .env or the process env) can't
    silently override a real built-in default with ''."""
    return {k: v for k, v in d.items() if v != ""}


def _cast(name: str, raw: str, kind):
    try:
        return kind(raw)
    except ValueError as e:
        raise ValueError(f"config value {name}={raw!r} is not a valid {kind.__name__}") from e


def _read_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = _strip_quotes(v.strip())
    return env


def _normalize_base_url(raw: str) -> str:
    """Resolve the configured endpoint to a full OpenAI-compatible base URL.

    A bare host:port gets `/v1` appended, because that is where Ollama, llama.cpp and
    vLLM all serve the OpenAI-compatible surface. An explicit path is respected as
    given, so a gateway that mounts the API somewhere else still works.
    """
    url = raw.rstrip("/")
    rest = url.split("://", 1)[-1]
    has_path = "/" in rest
    return url if has_path else f"{url}/v1"


# Keys retired on 2026-09-11, when the client contract was decoupled from Ollama: the
# contract is an OpenAI-compatible endpoint, and the runner behind it is replaceable.
# OLLAMA_HOST also collided with Ollama's own server-side bind address, which uses that
# exact name on the box -- two different meanings, one name.
_RENAMED = {
    "OLLAMA_HOST": (
        "INFERENCE_BASE_URL",
        "include the /v1 suffix, e.g. INFERENCE_BASE_URL=http://localhost:11434/v1",
    ),
    "OLLAMA_API_KEY": ("INFERENCE_API_KEY", "same value, new name"),
    "MODEL": ("INFERENCE_MODEL", "prefer a server-side alias over a runner-specific pull tag"),
    "EMBED_MODEL": ("INFERENCE_EMBED_MODEL", "same value, new name"),
}


def _check_renamed_keys(dotenv_values: dict[str, str]) -> None:
    """Fail loudly on a stale .env key instead of silently using the built-in default.

    Only the .env file is checked, not the process environment: `OLLAMA_HOST` is a
    legitimate *server-side* variable on the box, and a .env that sets both the old and
    the new name is fine -- the new one wins.
    """
    for old, (new, hint) in _RENAMED.items():
        if old in dotenv_values and new not in dotenv_values:
            raise ValueError(
                f"{old} is no longer read. Rename it to {new} in your .env "
                f"({hint}) -- see .env.example."
            )


@dataclass(frozen=True)
class Config:
    inference_base_url: str
    inference_api_key: str
    model: str
    embed_model: str
    workspace: Path
    out: Path
    digest_days: int
    eval_pass_threshold: float
    baseline_model: str
    dictation_proxy_host: str
    dictation_proxy_port: int
    eval_judge_model: str = ""
    endpoint_alert_minutes: float = 3.0
    endpoint_alert_webhook: str = ""

    @property
    def base_url(self) -> str:
        return _normalize_base_url(self.inference_base_url)


def load_config(
    dotenv: Path | None = None,
    overrides: dict[str, str] | None = None,
) -> Config:
    dotenv_values = _non_empty(_read_dotenv(dotenv if dotenv is not None else REPO_ROOT / ".env"))
    merged = dict(_DEFAULTS)
    merged.update(dotenv_values)
    merged.update(_non_empty({k: os.environ[k] for k in _DEFAULTS if k in os.environ}))
    if overrides:
        merged.update(overrides)

    _check_renamed_keys(dotenv_values)

    out = Path(merged["OUT"])
    if not out.is_absolute():
        out = REPO_ROOT / out

    return Config(
        inference_base_url=merged["INFERENCE_BASE_URL"],
        inference_api_key=merged["INFERENCE_API_KEY"],
        model=merged["INFERENCE_MODEL"],
        embed_model=merged["INFERENCE_EMBED_MODEL"],
        workspace=Path(merged["WORKSPACE"]),
        out=out,
        digest_days=_cast("DIGEST_DAYS", merged["DIGEST_DAYS"], int),
        eval_pass_threshold=_cast("EVAL_PASS_THRESHOLD", merged["EVAL_PASS_THRESHOLD"], float),
        baseline_model=merged["BASELINE_MODEL"],
        dictation_proxy_host=merged["DICTATION_PROXY_HOST"],
        dictation_proxy_port=_cast("DICTATION_PROXY_PORT", merged["DICTATION_PROXY_PORT"], int),
        eval_judge_model=merged["EVAL_JUDGE_MODEL"],
        endpoint_alert_minutes=_cast("ENDPOINT_ALERT_MINUTES", merged["ENDPOINT_ALERT_MINUTES"], float),
        endpoint_alert_webhook=merged["ENDPOINT_ALERT_WEBHOOK"],
    )
