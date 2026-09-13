"""WP-H bakeoff harness: pure helpers, probes and timing against the stdlib mock, report shape."""
import json
from pathlib import Path

from aiserver import LLM, load_config
from eval.bakeoff import run as bk

REPO = Path(__file__).resolve().parent.parent


def test_percentile_nearest_rank():
    assert bk.percentile([5, 1, 3, 2, 4], 50) == 3
    assert bk.percentile([5, 1, 3, 2, 4], 90) == 5
    assert bk.percentile([], 50) is None and bk.percentile([None], 50) is None


def test_derive_rates():
    d = bk.derive({"usage": {"prompt_tokens": 20000, "completion_tokens": 101}, "ttft_s": 10.0, "total_s": 11.0})
    assert d["prefill_tok_s"] == 2000 and d["decode_tok_s"] == 100
    assert bk.derive({"usage": None, "ttft_s": None, "total_s": 1})["prefill_tok_s"] is None


def test_timing_prompts_share_text_but_never_a_prefix():
    a, b = bk.timing_prompt("ops_log", 1), bk.timing_prompt("ops_log", 2)
    assert a.splitlines()[0] != b.splitlines()[0]
    assert a.split("\n", 1)[1] == b.split("\n", 1)[1]


def test_schema_checker():
    assert bk.check_schema_output('{"severity":"high","count":3,"services":["a"]}')["conforms"]
    assert not bk.check_schema_output('{"severity":"high","count":3,"services":["a"],"notes":"x"}')["conforms"]
    assert not bk.check_schema_output('{"severity":"critical","count":3,"services":[]}')["conforms"]
    assert not bk.check_schema_output("nope")["parsed"]


def test_probes_run_against_the_stdlib_mock(mock_endpoint):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"INFERENCE_BASE_URL": mock_endpoint})
    recs = {r["probe"]: r for r in bk.phase_probes(LLM(cfg, retries=0), "mock-model", "mock")}
    assert set(recs) == {"tool_call", "json_schema", "streaming", "unknown_model", "oversize_prompt", "models_listing"}
    assert recs["models_listing"]["pass"] is True
    assert recs["tool_call"]["pass"] is False  # the mock returns plain "ok"


def test_report_renders_both_runners_side_by_side():
    recs = []
    for rn, ttft in (("ollama", 10.0), ("llamacpp", 8.0)):
        for doc in bk.LONG_CASES:
            recs += [{"runner": rn, "phase": "warm", "doc": doc, "rep": i, "ttft_s": ttft + i, "prompt_tokens": 20000,
                      "prefill_tok_s": 20000 / (ttft + i), "vram_peak_mib": 21000, "error": None} for i in range(5)]
        recs.append({"runner": rn, "phase": "decode", "doc": "decode", "decode_tok_s": 100.0, "error": None})
        recs.append({"runner": rn, "phase": "cold", "doc": "ops_log", "ready_s": 3.0, "ttft_s": ttft, "cold_total_s": 3.0 + ttft, "error": None})
        recs.append({"runner": rn, "phase": "probe", "probe": "json_schema", "pass": rn == "llamacpp", "why": None if rn == "llamacpp" else "keys"})
    text = bk.report(recs, today="2026-09-13")
    assert "| ops_log | llamacpp | 20000 | 10.00 | 12.00 | 12.00 |" in text
    assert "| json_schema | pass | FAIL (keys) |" in text  # runners sort: llamacpp, ollama


def test_load_records_reads_dirs_and_files(tmp_path):
    (tmp_path / "a.jsonl").write_text(json.dumps({"runner": "x"}) + "\n", encoding="utf-8")
    assert bk.load_records([tmp_path]) == [{"runner": "x"}]
