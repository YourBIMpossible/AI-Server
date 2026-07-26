from pickup_checker.gates import (
    check_gate,
    SHEET_MATCHING_GATE_V1, MARKUP_EXTRACTION_GATES_V1,
    REGION_COMPARISON_GATE_V1, QUEUE_USEFULNESS_GATE_V1,
)


def test_check_gate_passes_when_all_directions_satisfied():
    metrics = {"false_match_rate": 0.0, "match_recall": 0.97, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is True
    assert result["failures"] == []


def test_check_gate_fails_on_a_max_metric_exceeding_threshold():
    metrics = {"false_match_rate": 0.02, "match_recall": 0.97, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False
    assert any("false_match_rate" in f for f in result["failures"])


def test_check_gate_fails_on_a_min_metric_below_threshold():
    metrics = {"false_match_rate": 0.0, "match_recall": 0.80, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False
    assert any("match_recall" in f for f in result["failures"])


def test_check_gate_treats_none_metric_as_failure_not_pass():
    """A metric with no data must FAIL, never silently pass -- 'no data' is not
    evidence of success."""
    metrics = {"false_match_rate": None, "match_recall": 0.97, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False
    assert any("no data" in f for f in result["failures"])


def test_check_gate_treats_missing_metric_as_failure():
    """Same as None: a gate key with no corresponding metric is 'no data'."""
    metrics = {"match_recall": 0.97, "unmatched_rate": 0.05}  # false_match_rate absent
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False


def test_check_gate_ignores_extra_metrics_not_in_gate():
    metrics = {"false_match_rate": 0.0, "match_recall": 0.97, "unmatched_rate": 0.05,
                "unrelated_extra_metric": 999}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is True


def test_check_gate_boundary_value_exactly_at_threshold_passes():
    """<= for max, >= for min -- exactly-at-threshold must pass, not fail."""
    metrics = {"false_match_rate": 0.0, "match_recall": 0.95, "unmatched_rate": 0.10}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is True


def test_region_comparison_gate_v1_values_match_spec():
    assert REGION_COMPARISON_GATE_V1["false_clear_rate_max"] == 0.01
    assert REGION_COMPARISON_GATE_V1["false_flag_rate_max"] == 0.20
    assert REGION_COMPARISON_GATE_V1["indeterminate_rate_max"] == 0.25


def test_false_clear_bound_is_far_tighter_than_false_flag():
    """The safety asymmetry is the whole point: a false clear hides a real
    missed pickup; a false flag only costs review time."""
    assert (REGION_COMPARISON_GATE_V1["false_clear_rate_max"]
            < REGION_COMPARISON_GATE_V1["false_flag_rate_max"] / 10)


def test_every_gate_key_base_name_matches_a_real_metric_name():
    """Regression guard for the naming-mismatch bug: a gate key whose base name
    doesn't match the metric name makes check_gate report 'no data' for
    everything -- which still FAILS, but for a completely bogus reason, so it
    looks plausible while measuring nothing.

    Verified against the real emitter rather than a hand-written list.
    """
    from run_golden_eval import evaluate_region_comparison_metrics
    from pickup_checker.models import Verdict

    real_metrics = evaluate_region_comparison_metrics(
        [(Verdict.CHANGED, "CHANGED")]
    )
    for gate_key in REGION_COMPARISON_GATE_V1:
        base = gate_key.rsplit("_", 1)[0]
        assert base in real_metrics, (
            f"gate key '{gate_key}' -> base '{base}' has no matching metric; "
            f"emitter produces {sorted(real_metrics)}"
        )


def test_markup_extraction_gates_are_per_form_not_pooled():
    assert set(MARKUP_EXTRACTION_GATES_V1.keys()) == {"annotation", "flattened", "scanned"}
    assert MARKUP_EXTRACTION_GATES_V1["annotation"]["recall_min"] == 0.99
    assert MARKUP_EXTRACTION_GATES_V1["flattened"]["recall_min"] == 0.85
    assert MARKUP_EXTRACTION_GATES_V1["scanned"]["recall_min"] == 0.70


def test_sheet_matching_gate_forbids_any_false_match():
    assert SHEET_MATCHING_GATE_V1["false_match_rate_max"] == 0.00


def test_queue_usefulness_gate_v1_values_match_spec():
    assert QUEUE_USEFULNESS_GATE_V1["recall_at_full_queue_min"] == 1.00
    assert QUEUE_USEFULNESS_GATE_V1["recall_at_10_min"] == 0.80
    assert QUEUE_USEFULNESS_GATE_V1["mean_reciprocal_rank_min"] == 0.50
    assert QUEUE_USEFULNESS_GATE_V1["precision_at_10_min"] == 0.50
    assert QUEUE_USEFULNESS_GATE_V1["items_per_sheet_max"] == 15
