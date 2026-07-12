"""WP-F eval harness: rubric scoring, local runs vs a mock endpoint, and the routing report."""
from pathlib import Path

from aiserver import LLM, load_config
from eval.baseline import claude_baseline
from eval.report import routing_table, write_report
from eval.run import load_cases, run_cases
from eval.scoring import passed, score

REPO = Path(__file__).resolve().parent.parent


def _llm(url):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"OLLAMA_HOST": url})
    return LLM(cfg, retries=0)


def _cases_file(tmp_path, lines):
    p = tmp_path / "cases.jsonl"
    p.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return p


# --- scoring -------------------------------------------------------------
def test_score_full_and_partial_contains():
    assert score("alpha beta", {"contains": ["alpha", "beta"]}) == 1.0
    assert score("alpha", {"contains": ["alpha", "beta"]}) == 0.5


def test_score_contains_any_is_a_gate():
    assert score("alpha", {"contains": ["alpha"], "contains_any": ["x", "y"]}) == 0.0
    assert score("alpha y", {"contains": ["alpha"], "contains_any": ["x", "y"]}) == 1.0


def test_score_is_case_insensitive_and_empty_rubric_is_full():
    assert score("ALPHA", {"contains": ["alpha"]}) == 1.0
    assert score("whatever", {}) == 1.0


def test_score_matches_whole_word_not_substring():
    assert score("this looks spammy to me", {"contains_any": ["spam"]}) == 0.0
    assert score("this is spam", {"contains_any": ["spam"]}) == 1.0


def test_score_not_contains_gates_negated_matches_to_zero():
    rubric = {"contains_any": ["spam"], "not_contains": ["not spam"]}
    assert score("This is NOT spam", rubric) == 0.0
    assert score("This is spam", rubric) == 1.0


def test_score_escapes_regex_special_characters_in_terms():
    assert score("the total is $5.00", {"contains": ["$5.00"]}) == 1.0
    assert score("the total is $5x00", {"contains": ["$5.00"]}) == 0.0


def test_score_matches_a_term_that_is_itself_a_complete_identifier():
    # EVAL-3-REG: the code-bug case's rubric terms must still match the natural
    # "raises a ZeroDivisionError" phrasing after EVAL-3 switched to whole-word
    # matching -- "ZeroDivisionError" is a complete word in that sentence, even
    # though "division"/"zero" alone are only substrings of it.
    rubric = {"contains_any": ["zero", "divide by", "division", "ZeroDivisionError"]}
    assert score("Yes, this raises a ZeroDivisionError when b is 0.", rubric) == 1.0
    assert score("Yes, division by zero occurs.", rubric) == 1.0


def test_score_empty_term_in_not_contains_does_not_zero_everything():
    assert score("anything at all", {"not_contains": [""]}) == 1.0


def test_score_empty_term_in_contains_any_does_not_auto_pass():
    assert score("anything at all", {"contains_any": [""]}) == 0.0


def test_passed_threshold_is_inclusive():
    assert passed(0.8, 0.8) is True
    assert passed(0.79, 0.8) is False


# --- cases ---------------------------------------------------------------
def test_load_cases_skips_blank_lines(tmp_path):
    p = _cases_file(tmp_path, ['{"id":"a","task":"t","input":"hi","rubric":{}}', ""])
    cases = load_cases(p)
    assert len(cases) == 1 and cases[0]["id"] == "a"


def test_repo_cases_file_is_valid_and_sized():
    cases = load_cases(REPO / "eval" / "cases.jsonl")
    assert 15 <= len(cases) <= 25
    assert all({"id", "task", "input", "rubric"} <= set(c) for c in cases)
    assert len({c["id"] for c in cases}) == len(cases)  # unique ids


def test_load_cases_raises_value_error_naming_the_file_and_line(tmp_path):
    p = _cases_file(tmp_path, ['{"id":"a","task":"t","input":"hi","rubric":{}}', "{not valid json"])
    try:
        load_cases(p)
        assert False, "expected ValueError"
    except ValueError as e:
        assert str(p) in str(e)
        assert ":2:" in str(e)  # 1-based line number of the malformed line


# --- local runs against the mock endpoint --------------------------------
def test_run_cases_scores_each_case(mock_endpoint, tmp_path):
    p = _cases_file(
        tmp_path,
        [
            '{"id":"pass","task":"digest","input":"x","rubric":{"contains":["ok"]}}',
            '{"id":"fail","task":"digest","input":"x","rubric":{"contains":["absent"]}}',
        ],
    )
    results = run_cases(load_cases(p), _llm(mock_endpoint), threshold=0.8)
    by = {r.id: r for r in results}
    assert by["pass"].score == 1.0 and by["pass"].passed is True
    assert by["fail"].score == 0.0 and by["fail"].passed is False
    assert by["pass"].baseline is None  # no ANTHROPIC_API_KEY -> baseline skipped


# --- EVAL-1/4/5: baseline is scored+recorded, isolated, and model-configurable ---


def test_run_cases_scores_and_records_the_baseline(mock_endpoint, tmp_path, monkeypatch):
    seen_models = []

    def fake_baseline(prompt, *, api_key, model):
        seen_models.append(model)
        return "ok"

    monkeypatch.setattr("eval.run.claude_baseline", fake_baseline)
    p = _cases_file(tmp_path, ['{"id":"b","task":"digest","input":"x","rubric":{"contains":["ok"]}}'])
    results = run_cases(
        load_cases(p), _llm(mock_endpoint), threshold=0.8, baseline_key="fake-key", baseline_model="custom-model"
    )
    r = results[0]
    assert r.baseline == "ok"
    assert r.baseline_score == 1.0
    assert seen_models == ["custom-model"]


def test_run_cases_baseline_failure_does_not_abort_the_local_run(mock_endpoint, tmp_path, monkeypatch):
    def failing_baseline(prompt, *, api_key, model):
        raise RuntimeError("transient cloud error")

    monkeypatch.setattr("eval.run.claude_baseline", failing_baseline)
    p = _cases_file(tmp_path, ['{"id":"b","task":"digest","input":"x","rubric":{"contains":["ok"]}}'])
    results = run_cases(load_cases(p), _llm(mock_endpoint), threshold=0.8, baseline_key="fake-key")
    r = results[0]
    assert r.score == 1.0 and r.passed is True  # local result unaffected by the cloud failure
    assert r.baseline is None and r.baseline_score is None


# --- report / routing ----------------------------------------------------
def _mixed_results(mock_endpoint, tmp_path):
    p = _cases_file(
        tmp_path,
        [
            '{"id":"d1","task":"digest","input":"x","rubric":{"contains":["ok"]}}',
            '{"id":"c1","task":"classify","input":"x","rubric":{"contains":["absent"]}}',
        ],
    )
    return run_cases(load_cases(p), _llm(mock_endpoint), threshold=0.8)


def test_routing_table_marks_local_ok_vs_route(mock_endpoint, tmp_path):
    rows = routing_table(_mixed_results(mock_endpoint, tmp_path), threshold=0.8)
    rec = {task: recommendation for task, rate, recommendation in rows}
    assert rec["digest"] == "local OK"
    assert rec["classify"] == "route to Claude"


def test_write_report_contains_table_and_model(mock_endpoint, tmp_path):
    results = _mixed_results(mock_endpoint, tmp_path)
    out = tmp_path / "out" / "eval"
    report = write_report(results, threshold=0.8, model="mock-model", out_dir=out, today="2026-06-16")
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "digest" in text and "classify" in text
    assert "local OK" in text and "route to Claude" in text
    assert "mock-model" in text


def test_write_report_renders_the_baseline_instead_of_discarding_it(mock_endpoint, tmp_path, monkeypatch):
    monkeypatch.setattr("eval.run.claude_baseline", lambda prompt, *, api_key, model: "claude's own answer")
    p = _cases_file(tmp_path, ['{"id":"d1","task":"digest","input":"x","rubric":{"contains":["ok"]}}'])
    results = run_cases(load_cases(p), _llm(mock_endpoint), threshold=0.8, baseline_key="fake-key")
    out = tmp_path / "out" / "eval"
    report = write_report(results, threshold=0.8, model="mock-model", out_dir=out, today="2026-06-16")
    text = report.read_text(encoding="utf-8")
    assert "Claude baseline: on" in text
    assert "claude's own answer" in text  # EVAL-1: no longer paid-for-and-discarded


# --- baseline ------------------------------------------------------------
def test_claude_baseline_skipped_without_key(monkeypatch):
    # TEST-1: explicit even though the conftest autouse fixture already clears
    # this -- documents the requirement locally, not just via a suite-wide default.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert claude_baseline("hello", api_key=None) is None
