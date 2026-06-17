"""Run each eval case through the local model (and optionally a Claude baseline), score it.

CLI:  python -m eval.run        # scores eval/cases.jsonl against the local endpoint,
                                # then writes out/eval/report-YYYY-MM-DD.md
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, get_logger, load_config

from .baseline import claude_baseline
from .scoring import passed, score

CASES_FILE = Path(__file__).resolve().parent / "cases.jsonl"


@dataclass
class Result:
    id: str
    task: str
    score: float
    passed: bool
    output: str
    baseline: str | None = None


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_cases(
    cases: list[dict],
    llm: LLM,
    *,
    threshold: float,
    baseline_key: str | None = None,
) -> list[Result]:
    results: list[Result] = []
    for c in cases:
        output = llm.chat([{"role": "user", "content": c["input"]}], temperature=0)
        s = score(output, c.get("rubric", {}))
        baseline = claude_baseline(c["input"], api_key=baseline_key) if baseline_key else None
        results.append(
            Result(
                id=c["id"],
                task=c.get("task", "general"),
                score=s,
                passed=passed(s, threshold),
                output=output,
                baseline=baseline,
            )
        )
    return results


def main() -> int:
    cfg = load_config()
    log = get_logger("eval")
    cases = load_cases()
    threshold = cfg.eval_pass_threshold
    baseline_key = os.environ.get("ANTHROPIC_API_KEY")

    try:
        results = run_cases(cases, LLM(cfg), threshold=threshold, baseline_key=baseline_key)
    except Exception as e:  # endpoint down, etc. -- surface, don't write a misleading report
        print(f"[FAIL] eval run failed: {e}", file=sys.stderr)
        return 1

    from .report import write_report

    today = datetime.now().strftime("%Y-%m-%d")
    report = write_report(results, threshold=threshold, model=cfg.model, out_dir=cfg.out / "eval", today=today)
    n_pass = sum(1 for r in results if r.passed)
    log("eval", cases=len(results), passed=n_pass, threshold=threshold, baseline=bool(baseline_key))
    print(f"[OK] {n_pass}/{len(results)} cases passed (threshold {threshold}). Wrote {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
