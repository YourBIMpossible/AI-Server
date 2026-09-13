"""WP-F eval harness: rubric scoring, local runs vs a mock endpoint, and the routing report."""
from pathlib import Path

from aiserver import LLM, load_config
from eval.baseline import claude_baseline
from eval.report import routing_table, write_report
from eval.run import load_cases, run_cases
from eval.scoring import passed, score

REPO = Path(__file__).resolve().parent.parent


def _llm(url):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"INFERENCE_BASE_URL": url})
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
    # Widened from <=25 on 2026-09-13, deliberately: 10 hard/long cases were added so the
    # eval separates models (every model scored 17/17 on the original set).
    assert 15 <= len(cases) <= 40
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


# --- reasoning stripping (WP-F 2026-09-13) --------------------------------
from datetime import date  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402

from aiserver import LLMError  # noqa: E402
from eval.judge import judge, parse_verdict  # noqa: E402
from eval.longinputs import build  # noqa: E402
from eval.run import case_prompt  # noqa: E402
from eval.scoring import strip_reasoning  # noqa: E402


def test_strip_reasoning_removes_closed_blocks_any_case_and_tag():
    assert strip_reasoning("<think>scratch</think>answer") == "answer"
    assert strip_reasoning("<THINK>\nline1\nline2\n</Think>\n answer ") == "answer"
    assert strip_reasoning("<thinking>a</thinking>x<reasoning>b</reasoning>y") == "xy"


def test_strip_reasoning_unterminated_block_strips_to_end():
    assert strip_reasoning("<think>still going when the tokens ran out") == ""
    assert strip_reasoning("prefix <think>cut off") == "prefix"


def test_strip_reasoning_orphan_close_tag_drops_the_preamble():
    assert strip_reasoning("reasoning the template opened\n</think>\nfinal") == "final"


def test_strip_reasoning_leaves_plain_answers_alone():
    assert strip_reasoning("  plain answer  ") == "plain answer"
    assert strip_reasoning(None) == ""


def test_score_ignores_keywords_that_only_appear_in_scratch_work():
    out = "<think>maybe the answer is spam?</think>HAM"
    assert score(out, {"contains_any": ["spam"]}) == 0.0
    assert score(out, {"contains_any": ["ham"]}) == 1.0


def test_score_truncated_reasoning_is_a_miss():
    assert score("<think>the port is 9443, so", {"regex_full": r"\s*9443\s*"}) == 0.0


# --- new rubric gates ----------------------------------------------------
def test_regex_full_is_an_exact_format_gate():
    assert score(" 9443\n", {"regex_full": r"\s*9443\s*"}) == 1.0
    assert score("The port is 9443", {"regex_full": r"\s*9443\s*"}) == 0.0


def test_json_equals_requires_exact_value_and_tolerates_one_fence():
    rubric = {"json_equals": ["a", "b"]}
    assert score('["a", "b"]', rubric) == 1.0
    assert score('```json\n["a", "b"]\n```', rubric) == 1.0
    assert score('["b", "a"]', rubric) == 0.0
    assert score('Here you go: ["a", "b"]', rubric) == 0.0


def test_max_words_gate():
    assert score("one two three", {"max_words": 3}) == 1.0
    assert score("one two three four", {"max_words": 3}) == 0.0


def test_patterns_count_toward_the_graded_fraction():
    rubric = {"contains": ["alpha"], "patterns": [r"^X=1$", r"^Y=2$"]}
    assert score("alpha\nX=1\nY=2", rubric) == 1.0
    assert abs(score("alpha\nX=1\nY=3", rubric) - 2 / 3) < 1e-9


# --- judge ---------------------------------------------------------------
class _FakeLLM:
    """Answers by substring of the prompt; records calls. Exceptions are raised."""

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def chat(self, messages, *, model=None, temperature=0.2, **opts):
        prompt = messages[-1]["content"]
        self.calls.append({"model": model, "temperature": temperature, "prompt": prompt, **opts})
        for key, reply in self.replies:
            if key in prompt:
                if isinstance(reply, Exception):
                    raise reply
                return reply
        return "ok"


def test_parse_verdict():
    assert parse_verdict("PASS") is True
    assert parse_verdict("fail\nbecause") is False
    assert parse_verdict("**PASS** the answer is right") is True
    assert parse_verdict("<think>FAIL? no</think>PASS") is True
    assert parse_verdict("The answer passes") is None
    assert parse_verdict("") is None


def test_judge_is_deterministic_and_unparseable_is_fail():
    llm = _FakeLLM([("CRITERION", "maybe")])
    ok, raw = judge(llm, "must say 400", "400 days", model="judge-m")
    assert ok is False and raw == "maybe"
    call = llm.calls[0]
    assert call["temperature"] == 0 and call["seed"] == 0 and call["model"] == "judge-m"
    assert "must say 400" in call["prompt"] and "400 days" in call["prompt"]


def _judge_case(tmp_path, rubric):
    return load_cases(_cases_file(tmp_path, [json.dumps({"id": "j", "task": "rag", "input": "Q?", "rubric": rubric})]))


def test_judge_fail_zeroes_a_keyword_pass(tmp_path):
    cases = _judge_case(tmp_path, {"contains": ["400"], "judge": "400 days is current"})
    answer = _FakeLLM([("Q?", "90 days, not 400")])
    grader = _FakeLLM([("CRITERION", "FAIL")])
    r = run_cases(cases, answer, threshold=0.8, judge_llm=grader)[0]
    assert r.keyword_score == 1.0 and r.judged is False
    assert r.score == 0.0 and r.passed is False


def test_judge_pass_keeps_the_keyword_score_and_cannot_rescue_a_miss(tmp_path):
    cases = _judge_case(tmp_path, {"contains": ["400"], "judge": "400 days is current"})
    ok = run_cases(cases, _FakeLLM([("Q?", "400 days")]), threshold=0.8, judge_llm=_FakeLLM([("CRITERION", "PASS")]))[0]
    assert ok.score == 1.0 and ok.passed and ok.judged is True
    miss = run_cases(cases, _FakeLLM([("Q?", "90 days")]), threshold=0.8, judge_llm=_FakeLLM([("CRITERION", "PASS")]))[0]
    assert miss.score == 0.0 and not miss.passed


def test_judge_runs_after_all_answers(tmp_path):
    lines = [json.dumps({"id": f"c{i}", "task": "t", "input": f"Q{i}?", "rubric": {"judge": "x"}}) for i in range(3)]
    shared = _FakeLLM([("CRITERION", "PASS")])
    run_cases(load_cases(_cases_file(tmp_path, lines)), shared, threshold=0.8)
    kinds = ["judge" if "CRITERION" in c["prompt"] else "answer" for c in shared.calls]
    assert kinds == ["answer"] * 3 + ["judge"] * 3


def test_judge_against_the_stdlib_mock_fails_closed(mock_endpoint, tmp_path):
    # The mock answers "ok" to everything: not a verdict, so the judged case must fail.
    cases = _judge_case(tmp_path, {"contains": ["ok"], "judge": "anything"})
    r = run_cases(cases, _llm(mock_endpoint), threshold=0.8)[0]
    assert r.keyword_score == 1.0 and r.judged is False and r.passed is False


def test_a_case_error_scores_zero_without_aborting_the_run(tmp_path):
    lines = [
        '{"id":"boom","task":"t","input":"BOOM","rubric":{}}',
        '{"id":"fine","task":"t","input":"x","rubric":{"contains":["ok"]}}',
    ]
    llm = _FakeLLM([("BOOM", LLMError("empty response"))])
    by = {r.id: r for r in run_cases(load_cases(_cases_file(tmp_path, lines)), llm, threshold=0.8)}
    assert by["boom"].error and by["boom"].score == 0.0 and not by["boom"].passed
    assert by["fine"].passed


# --- long documents: deterministic, and noise can never forge an answer ---
def test_documents_are_deterministic():
    build.cache_clear()
    first = {n: build(n) for n in ("ops_log", "worker_log", "docs_corpus")}
    build.cache_clear()
    assert first == {n: build(n) for n in first}


def test_ops_log_planted_facts():
    log = build("ops_log")
    failed_0812 = re.findall(r"^2026-08-12T\S+ ERROR \[deployer\] deploy DEP-\d+ env=prod status=FAILED", log, re.M)
    assert len(failed_0812) == 7
    deploy_lines = [ln for ln in log.splitlines() if re.search(r"deploy|DEP-", ln)]
    assert len(deploy_lines) == 27 and all("[deployer]" in ln for ln in deploy_lines)  # never filler
    assert not re.search(r"^2026-08-20T\S+ .*env=prod status=SUCCEEDED", log, re.M)
    assert len(re.findall(r"customer-facing|returning 503 to customers", log)) == 2
    assert len(set(re.findall(r"INC-\d+", log))) == 4
    assert "PostgreSQL 17" in log


def test_worker_log_planted_facts_match_the_case_answer():
    ids = sorted(re.findall(r"ERROR \[billing-worker\] job invoice-run failed code=E_TIMEOUT req=(R-\d+)", build("worker_log")))
    case = next(c for c in load_cases(REPO / "eval" / "cases.jsonl") if c["id"] == "long-extract-worker-errors")
    assert ids == case["rubric"]["json_equals"]
    assert build("worker_log").count("billing-") == 18  # 17 planted error/warn lines + 1 retry note


def test_docs_corpus_only_planted_docs_mention_audit_or_retention():
    docs = build("docs_corpus").split("\n\n")
    hits = [d.split("]")[0] for d in docs if re.search(r"audit|retention|retained", d, re.I)]
    assert hits == ["[DOC-041", "[DOC-077", "[DOC-118", "[DOC-124"]


def test_repo_cases_are_well_formed():
    for c in load_cases(REPO / "eval" / "cases.jsonl"):
        rubric = c["rubric"]
        if "regex_full" in rubric:
            re.compile(rubric["regex_full"])
        for p in rubric.get("patterns", []):
            re.compile(p)
        if "document" in c:
            assert "{{DOCUMENT}}" in c["input"]
            assert len(case_prompt(c)) > 40_000


def test_business_day_case_premise_holds():
    assert date(2026, 3, 20).weekday() == 4  # the case says Friday
