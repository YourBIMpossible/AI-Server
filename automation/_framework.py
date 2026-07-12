"""Tiny job framework: subclass Job, set name + schedule, implement run(); register it.

Drop-in pattern -- a new automation is three lines plus the run() body:

    from automation._framework import Job, register

    @register
    class MyJob(Job):
        name = "my-job"             # how `python -m automation my-job` finds it
        schedule = "daily 08:00"    # human hint, used by register-tasks-windows.ps1
        def run(self):
            out = self.out_dir / "result.md"   # out/<name>/ -- created for you
            out.write_text(self.llm.chat([...]), encoding="utf-8")
            return out

Then add `from . import my_job` to automation/__main__.py so it registers on startup, and
one row to register-tasks-windows.ps1 for its schedule. Jobs are read-only on the workspace;
every output goes under out/.
"""
from __future__ import annotations

import time
from pathlib import Path

from aiserver import LLM, Config, get_logger, load_config

REGISTRY: dict[str, type["Job"]] = {}


class JobPreconditionError(RuntimeError):
    """A job's required input (a directory, an index, etc.) is missing or invalid --
    distinct from LLMError so the CLI can give it its own clear [FAIL] message."""


def register(cls: type["Job"]) -> type["Job"]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a non-empty `name`")
    REGISTRY[cls.name] = cls
    return cls


def job_names() -> list[str]:
    return sorted(REGISTRY)


def run_job(name: str, cfg: Config | None = None) -> Path:
    if name not in REGISTRY:
        raise KeyError(f"unknown job '{name}'; known: {', '.join(job_names()) or '(none)'}")
    return REGISTRY[name](cfg).run()


class Job:
    name: str = ""
    schedule: str = ""

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.log = get_logger(self.name)
        self.llm = LLM(self.cfg)

    @property
    def out_dir(self) -> Path:
        """out/<name>/, created on demand. Jobs may write elsewhere under out/ if they prefer."""
        d = self.cfg.out / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def run(self) -> Path:
        raise NotImplementedError


def collect_logs(
    workspace: Path, days: int, *, per_file: int = 4000, cap: int = 24000
) -> tuple[list[str], str, bool]:
    """Gather recent BuildLog + decision-log markdown into (listed, corpus, any_root_found).
    Read-only.

    `any_root_found` is False only when NEITHER source directory exists under
    `workspace` -- distinct from both existing but having zero recent files, which
    is a genuinely quiet period, not a misconfigured WORKSPACE after relocation.
    """
    sources = [
        ("Build log", workspace / "BIMpossible_Workspace" / "01_BuildLog"),
        ("Decision log", workspace / "AI-Brain-Data" / "decision-log"),
    ]
    cutoff = time.time() - days * 86400
    listed: list[str] = []
    chunks: list[str] = []
    any_root_found = False
    for label, folder in sources:
        if not folder.exists():
            continue
        any_root_found = True
        files = [p for p in folder.glob("*.md") if p.is_file() and p.stat().st_mtime >= cutoff]
        for p in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
            listed.append(f"{label}: {p.name}")
            text = p.read_text(encoding="utf-8", errors="replace")[:per_file]
            chunks.append(f"### [{label}] {p.name}\n{text}")
    return listed, "\n\n".join(chunks)[:cap], any_root_found
