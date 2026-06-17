"""Revit weekly summary job -- the LOCAL-LLM version (WP-D3).

The existing `revit-log-weekly-processor` (AI-Brain-Data/Revit-AI/process_revit_logs.py) is a
deterministic parser: it writes templated daily summaries + a metrics-table weekly overview, and
calls no LLM. This job is the side-by-side LOCAL-LLM alternative: it reads those deterministic
daily summaries (read-only) and has the local model write a narrative weekly overview to
out/revit-weekly/. It does not touch the processor, its outputs, or the live Cowork schedule --
"cutover" is simply choosing to run/schedule this job. Read-only on AI-Brain-Data.

Run:  python -m automation revit-weekly
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from aiserver.prompts import REVIT_WEEKLY, render

from ._framework import Job, register


@register
class RevitWeeklyJob(Job):
    name = "revit-weekly"
    schedule = "Sat 07:45"
    days = 7

    def run(self) -> Path:
        src = self.cfg.workspace / "AI-Brain-Data" / "Revit-AI" / "daily-summaries"
        today = datetime.now().strftime("%Y-%m-%d")
        out_file = self.out_dir / f"revit-weekly-{today}.md"

        cutoff = time.time() - self.days * 86400
        files = (
            sorted(
                (p for p in src.glob("*.md") if p.is_file() and p.stat().st_mtime >= cutoff),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if src.exists()
            else []
        )

        if not files:
            out_file.write_text(
                f"# Revit weekly (local) — {today}\n\nNo Revit daily-summaries in the last "
                f"{self.days} days.\n",
                encoding="utf-8",
            )
            self.log("no-activity", out=str(out_file))
            return out_file

        corpus = "\n\n".join(
            f"### {p.name}\n{p.read_text(encoding='utf-8', errors='replace')[:4000]}" for p in files
        )[:24000]
        self.log("start", files=len(files), model=self.cfg.model)
        summary = self.llm.chat([{"role": "user", "content": render(REVIT_WEEKLY, corpus=corpus)}])
        body = (
            f"# Revit weekly (local) — {today}\n\n"
            f"_Local LLM summary of {len(files)} daily summaries · generated on {self.cfg.model}_\n\n"
            f"{summary}\n\n---\n\n## Source days\n"
            + "\n".join(f"- {p.name}" for p in files)
            + "\n"
        )
        out_file.write_text(body, encoding="utf-8")
        self.log("wrote", out=str(out_file), files=len(files))
        return out_file
