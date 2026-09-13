#!/usr/bin/env python3
"""Bring the endpoint to "serving" and warm the working model (WP-E).

The point is that the first real request of the day is not a cold load.

    python scripts/preload.py [--wait SECONDS] [--pull] [--model M ...]

1. Wait until GET /v1/models answers (portable -- any runner).
2. --pull: models from config/models.txt that the endpoint doesn't list are pulled with the
   runner's CLI when one is on PATH. That is runner-native, so it is best-effort enrichment:
   with no CLI it reports what's missing and carries on.
3. Warm each model (default: INFERENCE_MODEL) with a one-token completion; report seconds.

Exit status: 0 when every model warmed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # repo root for `aiserver`

from aiserver import LLM, LLMError, load_config  # noqa: E402

MODELS_FILE = REPO / "config" / "models.txt"


def wait_for(llm: LLM, seconds: float, *, sleep=time.sleep, clock=time.monotonic) -> bool:
    deadline = clock() + seconds
    while True:
        try:
            if llm.ping():
                return True
        except OSError:  # a timeout is not a URLError
            pass
        if clock() >= deadline:
            return False
        sleep(2)


def wanted_models(path: Path = MODELS_FILE) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _tagged(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def available_models(llm: LLM) -> list[str]:
    req = urllib.request.Request(f"{llm.cfg.base_url}/models", headers=llm._headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return [m["id"] for m in json.load(r).get("data", []) if m.get("id")]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return []


def missing_models(wanted: list[str], have: list[str]) -> list[str]:
    have_tagged = {_tagged(h) for h in have}
    return [w for w in wanted if _tagged(w) not in have_tagged]


def pull(models: list[str], cli: str | None) -> list[str]:
    """Pull with the runner CLI; returns the models still missing afterwards."""
    if not models:
        return []
    if cli is None:
        print(f"[WARN] not served and no runner CLI to pull with: {', '.join(models)}")
        return models
    left = []
    for m in models:
        print(f"[..] pulling {m}")
        if subprocess.run([cli, "pull", m]).returncode != 0:
            left.append(m)
    return left


def warm(llm: LLM, model: str) -> float:
    t0 = time.perf_counter()
    try:
        llm.chat([{"role": "user", "content": "Reply with OK."}], model=model, temperature=0, max_tokens=1)
    except LLMError as e:
        # A thinking model can spend its single token on reasoning and return no content.
        # The weights still loaded, which is all a warm-up is for.
        if "neither content nor tool_calls" not in str(e):
            raise
    return time.perf_counter() - t0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wait", type=float, default=120, help="seconds to wait for the endpoint")
    ap.add_argument("--pull", action="store_true", help="pull models in config/models.txt that aren't served")
    ap.add_argument("--model", action="append", help="model to warm (repeatable); default INFERENCE_MODEL")
    args = ap.parse_args(argv)

    cfg = load_config()
    llm = LLM(cfg, timeout=600, retries=0)
    if not wait_for(llm, args.wait):
        print(f"[FAIL] {cfg.base_url} did not answer /models within {args.wait:.0f}s", file=sys.stderr)
        return 1
    print(f"[OK] {cfg.base_url} answers /models")

    if args.pull:
        left = pull(missing_models(wanted_models(), available_models(llm)), shutil.which("ollama"))
        if left:
            print(f"[WARN] still missing: {', '.join(left)}")

    ok = True
    for model in args.model or [cfg.model]:
        try:
            print(f"[OK] warmed {model} in {warm(llm, model):.1f}s")
        except LLMError as e:
            ok = False
            print(f"[FAIL] could not warm {model}: {e}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
