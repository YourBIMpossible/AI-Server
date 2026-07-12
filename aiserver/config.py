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
    "OLLAMA_HOST": "http://localhost:11434",
    "MODEL": "qwen2.5-coder:14b",
    "EMBED_MODEL": "nomic-embed-text",
    "WORKSPACE": r"F:\AI-Dev",
    "OUT": "./out",
    "DIGEST_DAYS": "7",
    "EVAL_PASS_THRESHOLD": "0.8",
    "BASELINE_MODEL": "claude-opus-4-8",
    "DICTATION_PROXY_HOST": "127.0.0.1",
    "DICTATION_PROXY_PORT": "11435",
}


def _strip_quotes(v: str) -> str:
    """Strip one layer of matching outer quotes, e.g. MODEL="qwen2.5-coder:14b"."""
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


@dataclass(frozen=True)
class Config:
    ollama_host: str
    model: str
    embed_model: str
    workspace: Path
    out: Path
    digest_days: int
    eval_pass_threshold: float
    baseline_model: str
    dictation_proxy_host: str
    dictation_proxy_port: int

    @property
    def base_url(self) -> str:
        return self.ollama_host.rstrip("/")


def load_config(
    dotenv: Path | None = None,
    overrides: dict[str, str] | None = None,
) -> Config:
    merged = dict(_DEFAULTS)
    merged.update(_non_empty(_read_dotenv(dotenv if dotenv is not None else REPO_ROOT / ".env")))
    merged.update(_non_empty({k: os.environ[k] for k in _DEFAULTS if k in os.environ}))
    if overrides:
        merged.update(overrides)

    out = Path(merged["OUT"])
    if not out.is_absolute():
        out = REPO_ROOT / out

    return Config(
        ollama_host=merged["OLLAMA_HOST"],
        model=merged["MODEL"],
        embed_model=merged["EMBED_MODEL"],
        workspace=Path(merged["WORKSPACE"]),
        out=out,
        digest_days=_cast("DIGEST_DAYS", merged["DIGEST_DAYS"], int),
        eval_pass_threshold=_cast("EVAL_PASS_THRESHOLD", merged["EVAL_PASS_THRESHOLD"], float),
        baseline_model=merged["BASELINE_MODEL"],
        dictation_proxy_host=merged["DICTATION_PROXY_HOST"],
        dictation_proxy_port=_cast("DICTATION_PROXY_PORT", merged["DICTATION_PROXY_PORT"], int),
    )
