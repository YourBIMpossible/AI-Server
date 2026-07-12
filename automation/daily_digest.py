"""Daily digest job: summarize the last N days of BuildLog + decision-log activity.

WP-A's logic, now a framework Job. Output is unchanged: out/digest-YYYY-MM-DD.md (kept in
the out/ root rather than out/daily-digest/ to preserve the original behaviour).

Run:  python -m automation daily-digest
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aiserver.prompts import DIGEST, render

from ._framework import Job, collect_logs, register


@register
class DigestJob(Job):
    name = "daily-digest"
    schedule = "daily 07:00"

    def run(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        self.cfg.out.mkdir(parents=True, exist_ok=True)
        out_file = self.cfg.out / f"digest-{today}.md"
        listed, corpus, any_root_found = collect_logs(self.cfg.workspace, self.cfg.digest_days)

        if not any_root_found:
            # A wrong WORKSPACE after relocation must not look identical to a
            # genuinely quiet week -- neither source directory existing at all is
            # a configuration problem, not "no activity" (AUTO-6).
            out_file.write_text(
                f"# Daily digest — {today}\n\n**WORKSPACE roots not found** (looked under "
                f"`{self.cfg.workspace}`) — neither BuildLog nor decision-log exists there. "
                f"Check WORKSPACE in `.env` (see relocate.md) before trusting a future "
                f"\"No activity\" digest.\n",
                encoding="utf-8",
            )
            self.log("workspace-roots-not-found", out=str(out_file), workspace=str(self.cfg.workspace))
            return out_file

        if not corpus.strip():
            out_file.write_text(
                f"# Daily digest — {today}\n\nNo build-log or decision-log "
                f"activity in the last {self.cfg.digest_days} days.\n",
                encoding="utf-8",
            )
            self.log("no-activity", out=str(out_file))
            return out_file

        self.log("start", files=len(listed), model=self.cfg.model)
        summary = self.llm.chat([{"role": "user", "content": render(DIGEST, corpus=corpus)}])
        body = (
            f"# Daily digest — {today}\n\n"
            f"_Last {self.cfg.digest_days} days · {len(listed)} files · generated locally on "
            f"{self.cfg.model}_\n\n"
            f"{summary}\n\n---\n\n## Sources\n"
            + "\n".join(f"- {s}" for s in listed)
            + "\n"
        )
        out_file.write_text(body, encoding="utf-8")
        self.log("wrote", out=str(out_file), files=len(listed))
        return out_file
