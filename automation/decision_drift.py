"""Decision-drift job: a scheduled wrapper over rag/drift.py.

Surfaces decision-log entries with no strong match in the canonical docs. Writes the same
report as `python -m rag.drift` (out/rag/drift-YYYY-MM-DD.md), on a schedule. Requires the
RAG index to exist (run `python -m rag.ingest` first / on its own schedule).

Run:  python -m automation decision-drift
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rag.drift import DEFAULT_THRESHOLD, analyze, flag, write_report
from rag.store import VectorStore

from ._framework import Job, register


@register
class DriftJob(Job):
    name = "decision-drift"
    schedule = "Sat 07:30"

    def run(self) -> Path:
        decision_root = self.cfg.workspace / "AI-Brain-Data" / "decision-log"
        rag_out = self.cfg.out / "rag"  # same location as the standalone rag.drift tool
        store = VectorStore(rag_out / "index.db")
        items = analyze(
            decision_root, store, self.llm.embed, exclude_prefixes=(str(decision_root),)
        )
        store.close()

        today = datetime.now().strftime("%Y-%m-%d")
        report = write_report(items, DEFAULT_THRESHOLD, rag_out, today)
        self.log(
            "drift",
            decisions=len(items),
            flagged=len(flag(items, DEFAULT_THRESHOLD)),
            report=str(report),
        )
        return report
