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

from .baseline import DEFAULT_BASELINE_MODEL, claude_baseline
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
    baseline_score: float | None = None


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    """Parse cases.jsonl, one JSON object per non-blank line.

    Raises ValueError naming the file and 1-based line number on a malformed line,
    instead of letting json.JSONDecodeError's own message (which doesn't know the
    source file) surface as an unattributed traceback.
    """
    cases = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {e}") from e
    return cases


def run_cases(
    cases: list[dict],
    llm: LLM,
    *,
    threshold: float,
    baseline_key: str | None = None,
    baseline_model: str = DEFAULT_BASELINE_MODEL,
) -> list[Result]:
    results: list[Result] = []
    for c in cases:
        output = llm.chat([{"role": "user", "content": c["input"]}], temperature=0)
        s = score(output, c.get("rubric", {}))
        baseline = None
        baseline_score = None
        if baseline_key:
            try:
                baseline = claude_baseline(c["input"], api_key=baseline_key, model=baseline_model)
            except Exception as e:
                # The Claude baseline is a best-effort comparison, not the harness's
                # job. A transient cloud error must not take down the local run that
                # already succeeded for this case.
                print(f"[WARN] Claude baseline failed for {c['id']}: {e}", file=sys.stderr)
            else:
                if baseline is not None:
                    baseline_score = score(baseline, c.get("rubric", {}))
        results.append(
            Result(
                id=c["id"],
                task=c.get("task", "general"),
                score=s,
                passed=passed(s, threshold),
                output=output,
                baseline=baseline,
                baseline_score=baseline_score,
            )
        )
    return results


def main() -> int:
    cfg = load_config()
    log = get_logger("eval")
    threshold = cfg.eval_pass_threshold
    baseline_key = os.environ.get("ANTHROPIC_API_KEY")

    try:
        cases = load_cases()
        results = run_cases(
            cases,
            LLM(cfg),
            threshold=threshold,
            baseline_key=baseline_key,
            baseline_model=cfg.baseline_model,
        )
    except Exception as e:  # malformed cases file, endpoint down, etc. -- surface, don't write a misleading report
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
