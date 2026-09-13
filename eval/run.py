"""Run each eval case through the local model (and optionally a Claude baseline), score it.

CLI:  python -m eval.run        # scores eval/cases.jsonl against the local endpoint,
                                # then writes out/eval/report-YYYY-MM-DD.md
                                # and out/eval/outputs-YYYY-MM-DD.jsonl (raw answers)

Two phases: every case is answered first, then rubrics with a "judge" criterion are graded.
Answer and judge models can differ, and on a 24GB card two ~20GB models can't both stay
resident -- interleaving them would reload a model on every case.

Whenever a judge is used, it is first run on eval/judge_calibration.jsonl (answers with known
verdicts) and the agreement is stamped on the report: a judge that can't grade the calibration
set can't be trusted on the cases either.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, LLMError, get_logger, load_config

from .baseline import DEFAULT_BASELINE_MODEL, claude_baseline
from .judge import judge
from .longinputs import build
from .scoring import passed, score

CASES_FILE = Path(__file__).resolve().parent / "cases.jsonl"
CALIBRATION_FILE = Path(__file__).resolve().parent / "judge_calibration.jsonl"
DOCUMENT_PLACEHOLDER = "{{DOCUMENT}}"


@dataclass
class Result:
    id: str
    task: str
    score: float
    passed: bool
    output: str
    baseline: str | None = None
    baseline_score: float | None = None
    tier: str = "basic"
    keyword_score: float | None = None
    judged: bool | None = None  # None: no judge criterion; else the judge's verdict
    judge_raw: str | None = None
    error: str | None = None
    elapsed_s: float | None = None


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    """Parse a JSONL file, one JSON object per non-blank line.

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


def case_prompt(case: dict) -> str:
    """The case's input, with its generated long document substituted in if it names one."""
    text = case["input"]
    if "document" in case:
        text = text.replace(DOCUMENT_PLACEHOLDER, build(case["document"]))
    return text


def calibrate_judge(judge_llm, judge_model: str | None, path: Path = CALIBRATION_FILE) -> dict:
    """Run the judge on answers with known verdicts -> {agree, total, disagreements: [ids]}."""
    items = load_cases(path)
    wrong = []
    for item in items:
        try:
            verdict, _ = judge(judge_llm, item["criterion"], item["answer"], model=judge_model)
        except LLMError:
            verdict = None
        if verdict is not item["expected"]:
            wrong.append(item["id"])
    return {"agree": len(items) - len(wrong), "total": len(items), "disagreements": wrong}


def run_cases(
    cases: list[dict],
    llm: LLM,
    *,
    threshold: float,
    baseline_key: str | None = None,
    baseline_model: str = DEFAULT_BASELINE_MODEL,
    judge_llm=None,
    judge_model: str | None = None,
) -> list[Result]:
    judge_llm = judge_llm or llm
    results: list[Result] = []
    for c in cases:
        prompt = case_prompt(c)
        rubric = c.get("rubric", {})
        t0 = time.perf_counter()
        error = None
        try:
            output = llm.chat([{"role": "user", "content": prompt}], temperature=0)
        except LLMError as e:
            # One case the model can't answer (empty reply, timeout) scores 0; it doesn't
            # abort the run. main() still fails when *every* case errors -- endpoint down.
            output, error = "", str(e)
        elapsed = time.perf_counter() - t0
        baseline = None
        baseline_score = None
        if baseline_key:
            try:
                baseline = claude_baseline(prompt, api_key=baseline_key, model=baseline_model)
            except Exception as e:
                # The Claude baseline is a best-effort comparison, not the harness's
                # job. A transient cloud error must not take down the local run that
                # already succeeded for this case.
                print(f"[WARN] Claude baseline failed for {c['id']}: {e}", file=sys.stderr)
            else:
                if baseline is not None:
                    baseline_score = score(baseline, rubric)
        s = 0.0 if error else score(output, rubric)  # an empty rubric must not pass a failed call
        results.append(
            Result(
                id=c["id"],
                task=c.get("task", "general"),
                score=s,
                passed=passed(s, threshold),
                output=output,
                baseline=baseline,
                baseline_score=baseline_score,
                tier=c.get("tier", "basic"),
                keyword_score=s,
                error=error,
                elapsed_s=round(elapsed, 2),
            )
        )

    # Phase 2: the judge is a gate on top of the keyword score, never a way around it.
    criteria = {c["id"]: c["rubric"]["judge"] for c in cases if c.get("rubric", {}).get("judge")}
    for r in results:
        criterion = criteria.get(r.id)
        if criterion is None:
            continue
        if r.error:
            r.judged = False
        else:
            try:
                r.judged, r.judge_raw = judge(judge_llm, criterion, r.output, model=judge_model)
            except LLMError as e:
                r.judged, r.judge_raw = False, f"judge error: {e}"
        if not r.judged:
            r.score = 0.0
            r.passed = False
        if r.baseline is not None and r.baseline_score:
            try:
                ok, _ = judge(judge_llm, criterion, r.baseline, model=judge_model)
            except LLMError:
                ok = False
            if not ok:
                r.baseline_score = 0.0
    return results


def write_outputs(path: Path, results: list[Result], *, model: str, judge_model: str | None) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({"model": model, "judge_model": judge_model, **asdict(r)}) + "\n")


def main() -> int:
    cfg = load_config()
    log = get_logger("eval")
    threshold = cfg.eval_pass_threshold
    baseline_key = os.environ.get("ANTHROPIC_API_KEY")
    judge_model = cfg.eval_judge_model or cfg.model
    llm = LLM(cfg, timeout=900)

    try:
        cases = load_cases()
        results = run_cases(
            cases,
            llm,
            threshold=threshold,
            baseline_key=baseline_key,
            baseline_model=cfg.baseline_model,
            judge_model=judge_model,
        )
        calibration = (
            calibrate_judge(llm, judge_model) if any(c.get("rubric", {}).get("judge") for c in cases) else None
        )
    except Exception as e:  # malformed cases file, etc. -- surface, don't write a misleading report
        print(f"[FAIL] eval run failed: {e}", file=sys.stderr)
        return 1
    if results and all(r.error for r in results):
        print(f"[FAIL] every case errored; first: {results[0].error}", file=sys.stderr)
        return 1

    from .report import write_report

    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = cfg.out / "eval"
    report = write_report(
        results, threshold=threshold, model=cfg.model, out_dir=out_dir, today=today,
        judge_model=judge_model, calibration=calibration,
    )
    write_outputs(out_dir / f"outputs-{today}.jsonl", results, model=cfg.model, judge_model=judge_model)
    n_pass = sum(1 for r in results if r.passed)
    log("eval", cases=len(results), passed=n_pass, threshold=threshold, baseline=bool(baseline_key))
    print(f"[OK] {n_pass}/{len(results)} cases passed (threshold {threshold}). Wrote {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
