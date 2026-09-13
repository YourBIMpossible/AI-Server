"""scout/evidence.py + scout/report.py + scout/prompts: schema validation, fact/inference
separation, answer parsing, deterministic rendering."""
import json

import pytest

from scout import prompts
from scout.evidence import (EVIDENCE_SCHEMA, EvidenceLog, extract_symbols, normalize_report, parse_final_answer,
                            validate_evidence_document)
from scout.report import ARTIFACTS, evidence_document, write_artifacts


def _meta(**over):
    base = {"task": "do x", "model": "m", "runtime": "http://h:1", "prompt_version": "v1", "timestamp": "2026-09-13T00:00:00+00:00",
            "git_sha": "abc", "target": "/r", "tool_calls": [], "checks_run": [], "transcript": None}
    return {**base, **over}


def test_evidence_log_ids_are_sequential_and_sorted():
    log = EvidenceLog(sha="deadbeef")
    a = log.add(kind="file", tool="read_file", args={"path": "a.py", "start_line": 1}, excerpt="x" * 5000, path="a.py", lines=[1, 3])
    b = log.add(kind="search", tool="search_text", args={"pattern": "p"}, excerpt="hit")
    assert (a.id, b.id) == ("E1", "E2") and a.sha == "deadbeef" and len(a.excerpt) == 1200
    assert log.ids() == {"E1", "E2"}
    assert [e["id"] for e in log.to_obj()] == ["E1", "E2"]
    with pytest.raises(ValueError):
        log.add(kind="magic", tool="t", args={}, excerpt="")


def test_validate_evidence_document_catches_bad_shapes():
    log = EvidenceLog(sha=None)
    log.add(kind="git", tool="git_status", args={}, excerpt="")
    doc = evidence_document(_meta(), log.to_obj(), normalize_report({}, set()))
    assert validate_evidence_document(doc) == []
    bad = json.loads(json.dumps(doc))
    bad["schema"] = "nope"
    bad["evidence"].append({"id": "E1", "kind": "file", "tool": "t", "args": {}, "excerpt": ""})
    bad["evidence"].append({"id": "x", "kind": "file", "tool": "t", "args": {}, "excerpt": 3, "lines": [1]})
    del bad["metadata"]["git_sha"]
    errs = validate_evidence_document(bad)
    assert any("schema" in e for e in errs) and any("duplicate" in e for e in errs)
    assert any("id invalid" in e for e in errs) and any("lines" in e for e in errs) and any("git_sha" in e for e in errs)
    assert validate_evidence_document({"schema": EVIDENCE_SCHEMA, "metadata": {}, "evidence": "no"})


def test_parse_final_answer_fenced_bare_and_garbage():
    assert parse_final_answer('Here:\n```json\n{"summary": "s"}\n```\nthanks') == {"summary": "s"}
    assert parse_final_answer('prefix {"a": {"b": 1}} suffix') == {"a": {"b": 1}}
    assert parse_final_answer("no json here") is None
    assert parse_final_answer("[1, 2]") is None
    assert parse_final_answer("") is None


def test_normalize_demotes_uncited_facts_and_never_promotes():
    raw = {
        "summary": " s ",
        "facts": [
            {"claim": "cited", "evidence": ["E2", "E1", "E2"]},
            {"claim": "bogus cite", "evidence": ["E99"]},
            "bare string fact",
            {"claim": ""},
        ],
        "inferences": ["guess", {"claim": "guess2", "basis": "b"}],
        "unknowns": ["u1", 3, ""],
        "risks": [{"risk": "r", "severity": "CRITICAL"}, "plain risk"],
        "affected": {"tests": ["tests/test_x.py"], "bogus": ["x"]},
        "plan": [{"step": "do", "files": ["a.py"]}, "just a step"],
        "verification": ["run tests"],
        "next_actions": "single",
        "stop_reason": "",
    }
    rep = normalize_report(raw, {"E1", "E2"})
    assert rep["summary"] == "s"
    assert rep["facts"] == [{"claim": "cited", "evidence": ["E1", "E2"]}]
    assert rep["demoted"] == ["bogus cite", "bare string fact"]
    assert [i["claim"] for i in rep["inferences"]] == ["bogus cite", "bare string fact", "guess", "guess2"]
    assert rep["unknowns"] == ["u1", "3"]
    assert [r["severity"] for r in rep["risks"]] == ["medium", "medium"]
    assert rep["affected"]["tests"] == ["tests/test_x.py"] and "bogus" not in rep["affected"]
    assert rep["plan"][1]["step"] == "just a step" and rep["verification"][0]["check"] == "run tests"
    assert rep["next_actions"] == ["single"] and rep["stop_reason"] is None
    empty = normalize_report(None, set())
    assert empty["facts"] == [] and empty["stop_reason"] is None and set(empty["affected"]) == {"contracts", "config", "flags", "compat_boundaries", "migrations", "tests", "ops"}


def test_extract_symbols():
    src = "export async function fetchIt() {}\nclass A:\n    def m(self): ...\nfn go() {}\nstruct S;\n"
    assert extract_symbols(src) == ["fetchIt", "A", "m", "go", "S"]


def test_artifacts_are_deterministic_and_complete(tmp_path):
    log = EvidenceLog(sha="abc")
    log.add(kind="inventory", tool="list_files", args={"subdir": ""}, excerpt="a.py\t10", path=".", note="1 files")
    log.add(kind="file", tool="read_file", args={"path": "a.py"}, excerpt="def f(): pass", path="a.py", lines=[1, 1], symbols=["f"])
    rep = normalize_report({"summary": "sum", "facts": [{"claim": "f exists", "evidence": ["E2"]}], "unknowns": ["who calls f"],
                            "plan": [{"step": "add g", "files": ["a.py"], "rationale": "r", "risk": "low"}],
                            "verification": [{"check": "tests", "command": "pytest", "expected": "pass"}]}, log.ids())
    meta = _meta()
    a = write_artifacts(tmp_path / "one", meta, log.to_obj(), rep)
    b = write_artifacts(tmp_path / "two", meta, log.to_obj(), rep)
    assert [p.name for p in a] == list(ARTIFACTS)
    for x, y in zip(a, b):
        assert x.read_bytes() == y.read_bytes()
    pm = (tmp_path / "one" / "project-map.md").read_text(encoding="utf-8")
    assert "f exists — evidence: E2" in pm and "who calls f" in pm and "| E2 | file | read_file | a.py | 1-1 | f |" in pm
    doc = json.loads((tmp_path / "one" / "evidence.json").read_text(encoding="utf-8"))
    assert validate_evidence_document(doc) == [] and doc["metadata"]["git_sha"] == "abc"
    plan = (tmp_path / "one" / "implementation-plan.md").read_text(encoding="utf-8")
    assert "Step 1: add g" in plan and "`a.py`" in plan
    ver = (tmp_path / "one" / "verification-plan.md").read_text(encoding="utf-8")
    assert "| 1 | tests | `pytest` | pass |" in ver
    hand = (tmp_path / "one" / "handoff.md").read_text(encoding="utf-8")
    assert "do x" in hand and "facts demoted to inferences for missing/invalid citations: 0" in hand


def test_prompt_templates_render_with_json_braces_intact():
    sys_t = prompts.load("system")
    out = prompts.render(sys_t, tool_summary="- `read_file`: r", max_turns="3")
    assert '"facts": [{"claim"' in out and "{{" not in out and "`read_file`" in out
    with pytest.raises(KeyError):
        prompts.render("{{missing}}")
    task = prompts.render(prompts.load("task"), task="T", git_sha="s", seed_evidence="e", sources="(none)", checks="(none)")
    assert task.startswith("## Task (verbatim from the operator)\nT\n")
    assert prompts.PROMPT_VERSION == "v1"
