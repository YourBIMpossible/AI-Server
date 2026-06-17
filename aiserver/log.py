"""Tiny structured run logging to out/logs/<job>.log (JSON lines)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .config import load_config


def get_logger(job: str) -> Callable[..., None]:
    out = load_config().out / "logs"
    out.mkdir(parents=True, exist_ok=True)
    logfile = out / f"{job}.log"

    def log(event: str, **fields: Any) -> None:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "job": job,
            "event": event,
            **fields,
        }
        line = json.dumps(rec, default=str)
        with logfile.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line, file=sys.stderr)

    return log
