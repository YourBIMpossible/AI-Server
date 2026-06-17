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
}


def _read_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
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

    @property
    def base_url(self) -> str:
        return self.ollama_host.rstrip("/")


def load_config(
    dotenv: Path | None = None,
    overrides: dict[str, str] | None = None,
) -> Config:
    merged = dict(_DEFAULTS)
    merged.update(_read_dotenv(dotenv if dotenv is not None else REPO_ROOT / ".env"))
    merged.update({k: os.environ[k] for k in _DEFAULTS if k in os.environ})
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
        digest_days=int(merged["DIGEST_DAYS"]),
        eval_pass_threshold=float(merged["EVAL_PASS_THRESHOLD"]),
    )
