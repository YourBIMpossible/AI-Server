"""Aggregate eval results into a per-task routing report (WP-F).

A task is "local OK" when its pass-rate clears the threshold; otherwise "route to Claude".
"""
from __future__ import annotations

from pathlib import Path


def routing_table(results, threshold: float) -> list[tuple[str, float, str]]:
    """[(task, pass_rate, recommendation), ...] sorted by task."""
    by_task: dict[str, list] = {}
    for r in results:
        by_task.setdefault(r.task, []).append(r)
    rows: list[tuple[str, float, str]] = []
    for task in sorted(by_task):
        group = by_task[task]
        rate = sum(1 for r in group if r.passed) / len(group)
        recommendation = "local OK" if rate >= threshold else "route to Claude"
        rows.append((task, rate, recommendation))
    return rows


def write_report(results, *, threshold: float, model: str, out_dir: Path, today: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = routing_table(results, threshold)
    n_pass = sum(1 for r in results if r.passed)
    baseline_n = sum(1 for r in results if r.baseline is not None)

    lines = [
        f"# Eval report — {today}",
        "",
        f"_Local model: `{model}` · {n_pass}/{len(results)} cases passed · "
        f"pass threshold {threshold:.2f} · Claude baseline: "
        f"{'on' if baseline_n else 'skipped (no ANTHROPIC_API_KEY)'}._",
        "",
        "## Routing recommendation",
        "",
        "| Task | Local pass-rate | Recommendation |",
        "|------|-----------------|----------------|",
    ]
    for task, rate, recommendation in rows:
        lines.append(f"| {task} | {rate*100:.0f}% | {recommendation} |")

    lines += ["", "## Per-case results", "", "| Case | Task | Score | Passed | Baseline score |", "|------|------|-------|--------|----------------|"]
    for r in results:
        baseline_col = f"{r.baseline_score:.2f}" if r.baseline_score is not None else "—"
        lines.append(f"| {r.id} | {r.task} | {r.score:.2f} | {'yes' if r.passed else 'no'} | {baseline_col} |")
    lines.append("")

    if baseline_n:
        lines += ["## Claude baseline answers", ""]
        for r in results:
            if r.baseline is not None:
                lines += [f"### {r.id}", "", r.baseline, ""]

    report = out_dir / f"report-{today}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
