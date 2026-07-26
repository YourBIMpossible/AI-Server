"""Gate definitions and the generic check_gate evaluator.

Thresholds are copied VERBATIM from the design spec (section 11). Gate numbers
FREEZE before the first real golden-set run -- adjusting them after seeing
results is moving the goalposts and defeats the purpose of having a gate. Do not
change these without updating the spec first.
"""
from __future__ import annotations

# Suffix convention: "<metric>_max" means the metric must be <= value;
# "<metric>_min" means the metric must be >= value. check_gate() infers
# direction from the suffix, so no separate direction table can drift out of
# sync with the thresholds.

SHEET_MATCHING_GATE_V1 = {
    # Zero false matches is deliberate: an unmatched sheet is a visible review
    # item, but a WRONGLY matched sheet silently corrupts every finding built on
    # it while still looking plausible.
    "false_match_rate_max": 0.00,
    "match_recall_min": 0.95,
    "unmatched_rate_max": 0.10,
}

# Per-form, never pooled: pooling would let a near-perfect annotation score mask
# a weak scanned score. Scanned is EXPECTED to fail at v1.0 -- that is the
# correct outcome, meaning scanned input is not yet trusted.
MARKUP_EXTRACTION_GATES_V1 = {
    "annotation": {"recall_min": 0.99, "precision_min": 0.99, "bbox_iou_min": 0.95},
    "flattened": {"recall_min": 0.85, "precision_min": 0.80, "bbox_iou_min": 0.70},
    "scanned": {"recall_min": 0.70, "precision_min": 0.70, "bbox_iou_min": 0.60},
}

REGION_COMPARISON_GATE_V1 = {
    # Key base names MUST match the metric names emitted by
    # run_golden_eval.evaluate_region_comparison_metrics() -- "false_clear_rate",
    # not "false_clear". A mismatch makes check_gate report "no data" for every
    # metric, which still FAILS but for an entirely bogus reason. That exact bug
    # shipped briefly and was caught only by running the dashboard.
    #
    # false_clear_rate: tool said "fine" when the pickup was NOT done. This is
    # the dangerous failure -- it deletes a real missed pickup from the queue.
    "false_clear_rate_max": 0.01,
    # false_flag_rate: tool flagged something already handled. Costs review time
    # only, hence a 20x looser bound. The asymmetry IS the safety argument.
    "false_flag_rate_max": 0.20,
    "indeterminate_rate_max": 0.25,
}

QUEUE_USEFULNESS_GATE_V1 = {
    # Every known missed pickup must appear SOMEWHERE -- a tool that misses a
    # real miss is worse than no tool.
    "recall_at_full_queue_min": 1.00,
    # ...but recall alone is satisfied even if the real miss sits at position
    # 147, so rank-aware metrics guard the "scannable queue" goal.
    "recall_at_10_min": 0.80,
    "mean_reciprocal_rank_min": 0.50,
    "precision_at_10_min": 0.50,
    "items_per_sheet_max": 15,
}


def check_gate(metrics: dict, gate: dict) -> dict:
    """Evaluate metrics against a gate.

    `metrics` keys use the SAME base name as the gate keys, minus the _min/_max
    suffix -- e.g. metrics={"false_match_rate": 0.0} against gate key
    "false_match_rate_max".

    A metric that is None or absent counts as a FAILURE ("no data"), never as a
    pass: absence of evidence is not evidence of passing.
    """
    failures: list[str] = []
    for gate_key, threshold in gate.items():
        if gate_key.endswith("_max"):
            base, direction = gate_key[: -len("_max")], "max"
        elif gate_key.endswith("_min"):
            base, direction = gate_key[: -len("_min")], "min"
        else:
            continue  # unrecognized gate-key shape; skip defensively

        value = metrics.get(base)
        if value is None:
            failures.append(f"{base}: no data")
            continue
        if direction == "max" and value > threshold:
            failures.append(f"{base} {value:.3f} > {threshold}")
        elif direction == "min" and value < threshold:
            failures.append(f"{base} {value:.3f} < {threshold}")

    return {"pass": len(failures) == 0, "failures": failures}
