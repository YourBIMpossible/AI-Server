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


# --- baseline ------------------------------------------------------------
def test_claude_baseline_skipped_without_key():
    assert claude_baseline("hello", api_key=None) is None
