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


def _tier_line(results) -> str:
    tiers: dict[str, list] = {}
    for r in results:
        tiers.setdefault(getattr(r, "tier", "basic"), []).append(r)
    return " · ".join(
        f"{tier}: {sum(1 for r in group if r.passed)}/{len(group)}" for tier, group in sorted(tiers.items())
    )


def write_report(
    results, *, threshold: float, model: str, out_dir: Path, today: str, judge_model: str | None = None
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = routing_table(results, threshold)
    n_pass = sum(1 for r in results if r.passed)
    baseline_n = sum(1 for r in results if r.baseline is not None)
    judge_note = f"`{judge_model}`" if judge_model else "none"
    if judge_model and judge_model == model:
        judge_note += " (self-judged)"

    lines = [
        f"# Eval report — {today}",
        "",
        f"_Local model: `{model}` · {n_pass}/{len(results)} cases passed · "
        f"pass threshold {threshold:.2f} · judge: {judge_note} · Claude baseline: "
        f"{'on' if baseline_n else 'skipped (no ANTHROPIC_API_KEY)'}._",
        "",
        f"By tier — {_tier_line(results)}",
        "",
        "## Routing recommendation",
        "",
        "| Task | Local pass-rate | Recommendation |",
        "|------|-----------------|----------------|",
    ]
    for task, rate, recommendation in rows:
        lines.append(f"| {task} | {rate*100:.0f}% | {recommendation} |")

    lines += [
        "",
        "## Per-case results",
        "",
        "| Case | Task | Tier | Score | Keywords | Judge | Passed | Seconds | Baseline score |",
        "|------|------|------|-------|----------|-------|--------|---------|----------------|",
    ]
    for r in results:
        baseline_col = f"{r.baseline_score:.2f}" if r.baseline_score is not None else "—"
        judged = getattr(r, "judged", None)
        judge_col = "—" if judged is None else ("PASS" if judged else "FAIL")
        kw = getattr(r, "keyword_score", None)
        kw_col = f"{kw:.2f}" if kw is not None else "—"
        secs = getattr(r, "elapsed_s", None)
        secs_col = f"{secs:.1f}" if secs is not None else "—"
        err = " (error)" if getattr(r, "error", None) else ""
        lines.append(
            f"| {r.id} | {r.task} | {getattr(r, 'tier', 'basic')} | {r.score:.2f} | {kw_col} | {judge_col} | "
            f"{'yes' if r.passed else 'no'}{err} | {secs_col} | {baseline_col} |"
        )
    lines.append("")

    if baseline_n:
        lines += ["## Claude baseline answers", ""]
        for r in results:
            if r.baseline is not None:
                lines += [f"### {r.id}", "", r.baseline, ""]

    report = out_dir / f"report-{today}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
