#!/usr/bin/env python3
"""Smoke test: send one chat request to the local OpenAI-compatible endpoint.

Uses the `aiserver` package for config + HTTP (no inline .env/urllib). Run directly:
    python scripts/smoke-test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, LLMError, load_config


def main() -> int:
    cfg = load_config()
    llm = LLM(cfg)
    try:
        msg = llm.chat(
            [{"role": "user", "content": "Reply with exactly: AI-Server online."}],
            temperature=0,
        )
    except LLMError as e:
        print(
            f"[FAIL] {e}\n       Is Ollama running? Try: ollama serve",
            file=sys.stderr,
        )
        return 1
    print(f"[OK] {cfg.base_url}  model={cfg.model}")
    print(f"     model said: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
