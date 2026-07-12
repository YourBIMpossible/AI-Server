"""Weekly rollup job: a Monday status note over the week's BuildLog + decision-log.

Longer horizon than the daily digest. Output: out/weekly-rollup/rollup-YYYY-MM-DD.md.

Run:  python -m automation weekly-rollup
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aiserver.prompts import WEEKLY_ROLLUP, render

from ._framework import Job, collect_logs, register


@register
class RollupJob(Job):
    name = "weekly-rollup"
    schedule = "Mon 07:15"
    days = 7

    def run(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        out_file = self.out_dir / f"rollup-{today}.md"
        listed, corpus, any_root_found = collect_logs(self.cfg.workspace, self.days)

        if not any_root_found:
            # Same AUTO-6 guard as daily_digest.py -- collect_logs is shared, so the
            # wrong-WORKSPACE-looks-quiet risk was identical here even though the
            # audit only named the digest job.
            out_file.write_text(
                f"# Weekly rollup — {today}\n\n**WORKSPACE roots not found** (looked under "
                f"`{self.cfg.workspace}`) — neither BuildLog nor decision-log exists there. "
                f"Check WORKSPACE in `.env` (see relocate.md) before trusting a future "
                f"\"No activity\" rollup.\n",
                encoding="utf-8",
            )
            self.log("workspace-roots-not-found", out=str(out_file), workspace=str(self.cfg.workspace))
            return out_file

        if not corpus.strip():
            out_file.write_text(
                f"# Weekly rollup — {today}\n\nNo activity in the last {self.days} days.\n",
                encoding="utf-8",
            )
            self.log("no-activity", out=str(out_file))
            return out_file

        self.log("start", files=len(listed), model=self.cfg.model)
        summary = self.llm.chat(
            [{"role": "user", "content": render(WEEKLY_ROLLUP, corpus=corpus)}]
        )
        body = (
            f"# Weekly rollup — {today}\n\n"
            f"_Week ending {today} · {len(listed)} files · generated locally on "
            f"{self.cfg.model}_\n\n"
            f"{summary}\n\n---\n\n## Sources\n"
            + "\n".join(f"- {s}" for s in listed)
            + "\n"
        )
        out_file.write_text(body, encoding="utf-8")
        self.log("wrote", out=str(out_file), files=len(listed))
        return out_file
