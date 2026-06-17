#!/usr/bin/env python3
"""Smoke test: send one chat request to the local OpenAI-compatible endpoint."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env():
    env = {}
    f = Path(__file__).resolve().parent.parent / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    # real environment overrides .env
    for k in ("OLLAMA_HOST", "MODEL"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def main():
    env = load_env()
    host = env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = env.get("MODEL", "qwen2.5-coder:14b")
    url = f"{host}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: AI-Server online."}],
        "stream": False,
        "temperature": 0,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
        msg = data["choices"][0]["message"]["content"].strip()
        print(f"[OK] {host}  model={model}")
        print(f"     model said: {msg}")
    except urllib.error.URLError as e:
        print(
            f"[FAIL] Could not reach {url}\n       {e}\n"
            f"       Is Ollama running? Try: ollama serve",
            file=sys.stderr,
        )
        sys.exit(1)
    except (KeyError, json.JSONDecodeError) as e:
        print(f"[FAIL] Unexpected response shape: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
