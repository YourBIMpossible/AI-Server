from pickup_checker.models import Verdict
from run_golden_eval import evaluate_region_comparison_metrics


def test_evaluate_region_comparison_metrics_computes_rates_correctly():
    # (predicted_verdict, ground_truth) -- ground truth is BINARY per the spec's
    # labeling rubric; INDETERMINATE is a tool output only, never a label.
    labeled = [
        (Verdict.UNCHANGED, "UNCHANGED"),   # correct
        (Verdict.CHANGED, "CHANGED"),        # correct
        (Verdict.UNCHANGED, "CHANGED"),      # FALSE CLEAR -- the dangerous one
        (Verdict.CHANGED, "UNCHANGED"),      # false flag
    ]
    metrics = evaluate_region_comparison_metrics(labeled)
    assert metrics["false_clear_rate"] == 0.25  # 1 of 4
    assert metrics["false_flag_rate"] == 0.25   # 1 of 4
    assert metrics["indeterminate_rate"] == 0.0


def test_indeterminate_counts_as_review_load_not_as_wrong():
    """Spec rubric: INDETERMINATE is an abstain. It raises review load but is
    never scored as a false clear or false flag."""
    labeled = [
        (Verdict.INDETERMINATE, "CHANGED"),
        (Verdict.INDETERMINATE, "UNCHANGED"),
        (Verdict.CHANGED, "CHANGED"),
        (Verdict.UNCHANGED, "UNCHANGED"),
    ]
    metrics = evaluate_region_comparison_metrics(labeled)
    assert metrics["false_clear_rate"] == 0.0
    assert metrics["false_flag_rate"] == 0.0
    assert metrics["indeterminate_rate"] == 0.5


def test_empty_label_set_returns_none_metrics_not_zero():
    """No data must be None (which the gate treats as a FAILURE), never 0.0
    (which would look like a perfect score)."""
    metrics = evaluate_region_comparison_metrics([])
    assert metrics["false_clear_rate"] is None
    assert metrics["false_flag_rate"] is None
    assert metrics["indeterminate_rate"] is None


def test_empty_metrics_fail_the_gate():
    from pickup_checker.gates import REGION_COMPARISON_GATE_V1, check_gate

    metrics = evaluate_region_comparison_metrics([])
    result = check_gate(metrics, REGION_COMPARISON_GATE_V1)
    assert result["pass"] is False
