#!/usr/bin/env python3
"""Point-in-time AI-Server status for the Dashboard refresh (WP-D1).

The Dashboard is a static site refreshed by a *local* Claude session; it cannot poll the
LAN-only inference endpoint from the cloud. This helper runs DURING that local refresh and
prints a compact JSON snapshot the refresh embeds in `data.js`:

  - endpoint up/down + models available (`/api/tags`) and loaded (`/api/ps`)  -- LAN-only
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


def endpoint_status(cfg, timeout: float = 4.0) -> dict:
    """Poll the endpoint: up/down + available (/api/tags) and loaded (/api/ps) models."""
    tags = _fetch(cfg.base_url, "/api/tags", timeout)
    up = tags is not None
    return {
        "up": up,
        "host": cfg.base_url,
        "models_available": _names(tags),
        "models_loaded": _names(_fetch(cfg.base_url, "/api/ps", timeout)) if up else [],
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
