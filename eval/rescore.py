"""Re-grade saved answers against the current rubrics, without asking the model again.

    python -m eval.rescore out/eval/outputs-YYYY-MM-DD.jsonl [--out DIR]

Answers come from the outputs file eval.run wrote; rubrics and judge criteria come from the
current eval/cases.jsonl. The judge (EVAL_JUDGE_MODEL, else the answer model) is called
live and calibrated first. A grader fix therefore re-scores every model identically, and
nobody has to spend GPU hours regenerating answers that did not change.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, LLMError, load_config

from .report import write_report
from .run import calibrate_judge, case_prompt, load_cases, run_cases, write_outputs


class ReplayLLM:
    """Answers each case prompt with the saved output (or re-raises its saved error)."""

    def __init__(self, cases: list[dict], saved: dict[str, dict]):
        self._by_prompt = {case_prompt(c): saved[c["id"]] for c in cases if c["id"] in saved}

    def chat(self, messages, **_):
        rec = self._by_prompt[messages[-1]["content"]]
        if rec.get("error"):
            raise LLMError(rec["error"])
        return rec["output"]


def rescore(outputs: Path, *, threshold: float, judge_llm, judge_model: str | None):
    saved = {r["id"]: r for r in load_cases(outputs)}
    cases = [c for c in load_cases() if c["id"] in saved]
    results = run_cases(cases, ReplayLLM(cases, saved), threshold=threshold,
                        judge_llm=judge_llm, judge_model=judge_model)
    for r in results:  # keep the original answer timings
        r.elapsed_s = saved[r.id].get("elapsed_s")
    model = next(iter(saved.values())).get("model", "unknown")
    return results, model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outputs", type=Path)
    ap.add_argument("--out", type=Path, help="report directory (default: next to the outputs file)")
    args = ap.parse_args(argv)

    cfg = load_config()
    judge_model = cfg.eval_judge_model or None
    judge_llm = LLM(cfg, timeout=900)
    results, model = rescore(args.outputs, threshold=cfg.eval_pass_threshold,
                             judge_llm=judge_llm, judge_model=judge_model or cfg.model)
    judge_name = judge_model or model
    calibration = calibrate_judge(judge_llm, judge_name)
    out_dir = args.out or args.outputs.parent
    today = datetime.now().strftime("%Y-%m-%d")
    report = write_report(results, threshold=cfg.eval_pass_threshold, model=model, out_dir=out_dir,
                          today=f"{today}-rescored", judge_model=judge_name, calibration=calibration)
    write_outputs(out_dir / f"outputs-{today}-rescored.jsonl", results, model=model, judge_model=judge_name)
    n = sum(1 for r in results if r.passed)
    print(f"[OK] {model}: {n}/{len(results)} after rescoring; judge calibration "
          f"{calibration['agree']}/{calibration['total']}. Wrote {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
