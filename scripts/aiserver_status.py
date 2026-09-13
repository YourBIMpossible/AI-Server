#!/usr/bin/env python3
"""Point-in-time AI-Server status for the Dashboard refresh (WP-D1).

The Dashboard is a static site refreshed by a *local* Claude session; it cannot poll the
LAN-only inference endpoint from the cloud. This helper runs DURING that local refresh and
prints a compact JSON snapshot the refresh embeds in `data.js`:

  - endpoint up/down + models available (OpenAI-compatible `/v1/models`), plus loaded
    models when the runner happens to expose Ollama's `/api/ps`  -- LAN-only
  - the newest output of each automation job (digest / weekly-rollup / decision-drift)

Read-only. Run:  python scripts/aiserver_status.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import load_config

# job name -> (subdirectory under out/, filename prefix)
_JOBS = {
    "daily-digest": (".", "digest-"),
    "weekly-rollup": ("weekly-rollup", "rollup-"),
    "decision-drift": ("rag", "drift-"),
}
_META = re.compile(r"^_(.*)_$")


def _summary(path: Path) -> str:
    """One-line summary: the document's first heading + its italic metadata line, if any."""
    heading, meta = path.stem, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("# "):
            heading = line[2:].strip()
            break
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _META.match(line.strip())
        if m:
            meta = m.group(1).strip()
            break
    return f"{heading} — {meta}" if meta else heading


def _newest(folder: Path, prefix: str) -> Path | None:
    if not folder.exists():
        return None
    files = sorted(
        (p for p in folder.glob(f"{prefix}*.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def job_outputs(out: Path) -> dict:
    """Newest output of each job -> {file, modified(ISO), summary} or None when absent."""
    result: dict = {}
    for name, (subdir, prefix) in _JOBS.items():
        folder = out if subdir == "." else out / subdir
        newest = _newest(folder, prefix)
        if newest is None:
            result[name] = None
        else:
            ts = datetime.fromtimestamp(newest.stat().st_mtime)
            result[name] = {
                "file": newest.name,
                "modified": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "summary": _summary(newest),
            }
    return result


def _fetch(base_url: str, path: str, timeout: float):
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _names(data) -> list[str]:
    return [m.get("name") for m in (data.get("models") or []) if m.get("name")] if data else []


def _openai_model_ids(data) -> list[str]:
    return [m.get("id") for m in (data.get("data") or []) if m.get("id")] if data else []


def _server_root(base_url: str) -> str:
    """Strip the OpenAI path suffix to reach the runner's own root."""
    return base_url[: -len("/v1")] if base_url.endswith("/v1") else base_url


def endpoint_status(cfg, timeout: float = 4.0) -> dict:
    """Poll the endpoint.

    Liveness and the available-model list come from the portable `/models`, so this keeps
    working across runners. Loaded-model detail is Ollama's `/api/ps` with no OpenAI
    equivalent -- it is a best-effort enrichment, absent on other runners rather than a
    failure. Don't promote it into the portable path.
    """
    models = _fetch(cfg.base_url, "/models", timeout)
    up = models is not None
    loaded = _fetch(_server_root(cfg.base_url), "/api/ps", timeout) if up else None
    return {
        "up": up,
        "host": cfg.base_url,
        "models_available": _openai_model_ids(models),
        "models_loaded": _names(loaded),
        "models_loaded_supported": loaded is not None,
    }


def build_status(cfg) -> dict:
    return {
        "generated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "endpoint": endpoint_status(cfg),
        "jobs": job_outputs(cfg.out),
    }


def main() -> int:
    print(json.dumps(build_status(load_config()), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
