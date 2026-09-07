"""Golden-set dashboard: per-gate PASS/FAIL, version-stamped.

Synthesizes a tiny demo set when no real golden-set jobs are labeled yet, so the
harness is provable on day one rather than being dead code until labeling
happens. The demo set deliberately contains one false flag, so a run that
reports PASS on it would indicate the gate math is broken.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pickup_checker.gates import REGION_COMPARISON_GATE_V1, check_gate
from pickup_checker.models import Verdict

TOOL_VERSION = "0.1.0"
GOLDEN_SET_DIR = Path(__file__).parent / "golden_set"


def evaluate_region_comparison_metrics(labeled: list[tuple]) -> dict:
    """labeled: list of (predicted_verdict: Verdict, ground_truth: 'CHANGED'|'UNCHANGED').

    Returns None for every metric on an empty set -- the gate treats None as a
    failure ("no data"), which is correct: zero labels is not a perfect score.
    """
    n = len(labeled)
    if n == 0:
        return {"false_clear_rate": None, "false_flag_rate": None,
                "indeterminate_rate": None}

    # false clear: tool said UNCHANGED ("fine") when the truth is CHANGED.
    false_clears = sum(1 for pred, truth in labeled
                        if pred is Verdict.UNCHANGED and truth == "CHANGED")
    # false flag: tool said CHANGED when the truth is UNCHANGED.
    false_flags = sum(1 for pred, truth in labeled
                       if pred is Verdict.CHANGED and truth == "UNCHANGED")
    # INDETERMINATE is an abstain: review load, never scored wrong.
    indeterminate = sum(1 for pred, _ in labeled if pred is Verdict.INDETERMINATE)

    return {
        "false_clear_rate": false_clears / n,
        "false_flag_rate": false_flags / n,
        "indeterminate_rate": indeterminate / n,
    }


def _synthesize_demo_labels() -> list[tuple]:
    """Proves the harness runs end-to-end before any real labeling exists.
    Contains one deliberate false flag (25% > the 20% gate) so this demo set
    is EXPECTED to FAIL -- a PASS here means check_gate is broken."""
    return [
        (Verdict.UNCHANGED, "UNCHANGED"),
        (Verdict.CHANGED, "CHANGED"),
        (Verdict.UNCHANGED, "UNCHANGED"),
        (Verdict.CHANGED, "UNCHANGED"),  # deliberate false flag
    ]


def main() -> int:
    print(f"pickup_checker golden-set dashboard -- tool v{TOOL_VERSION}")

    labeled_jobs = sorted(GOLDEN_SET_DIR.glob("*/labels.json"))
    if labeled_jobs:
        print(f"\nfound {len(labeled_jobs)} labeled golden-set job(s):")
        for j in labeled_jobs:
            print(f"  {j.parent.name}")
        print("\nReal golden-set evaluation is NOT yet wired -- loading labels.json,")
        print("running the pipeline per job, and computing the sheet-matching,")
        print("markup-extraction and queue-usefulness metrics is the next step.")
        print("See golden_set/README.md for the labeling protocol.")
        return 0

    print("\nno labeled golden-set jobs found in golden_set/ -- using a synthetic demo set")
    print("(see golden_set/README.md to build the real GoldenSet v1.0)\n")

    demo_labels = _synthesize_demo_labels()
    metrics = evaluate_region_comparison_metrics(demo_labels)
    gate_result = check_gate(metrics, REGION_COMPARISON_GATE_V1)

    print("Region comparison gate:")
    for key, value in metrics.items():
        shown = "no data" if value is None else f"{value:.3f}"
        print(f"  {key}: {shown}")
    status = "PASS" if gate_result["pass"] else "FAIL: " + "; ".join(gate_result["failures"])
    print(f"  -> {status}")
    print("  (the demo set contains a deliberate false flag; FAIL here is CORRECT)\n")

    print("Sheet matching / markup extraction / queue usefulness gates: no data yet")
    print("(require real golden-set jobs -- see golden_set/README.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
