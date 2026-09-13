"""End-to-end: a fixture git repo, a mocked model that calls scout tools then answers with the
report JSON. Proves the artifacts name real files/symbols, carry the fixture SHA, keep facts and
inferences apart, record a known unknown, and that the fixture repo is untouched."""
import json
import os
import subprocess
import sys

import pytest

from aiserver import LLM, load_config
from scout.cli import main
from scout.evidence import validate_evidence_document
from scout.run import ARTIFACTS, ScoutInputs, run_scout
from scout.sandbox import SandboxError
from tests.conftest import _running, _sequenced_server


def _tool_call(name, arguments, call_id="call_1"):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}}]}


def _final(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture()
def fixture_repo(tmp_path):
    root = tmp_path / "fixture"
    (root / "svc").mkdir(parents=True)
    (root / "svc" / "__init__.py").write_text("")
    (root / "svc" / "export.py").write_text(
        "import csv\n\n\ndef export_rows(rows, path):\n    with open(path, 'w') as fh:\n        csv.writer(fh).writerows(rows)\n\n\nclass Exporter:\n    fmt = 'csv'\n"
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_export.py").write_text("def test_export():\n    assert True\n")
    (root / ".env").write_text("API_KEY=hunter2\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture: export service"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return root, sha


def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def _cfg(url, tmp_path):
    return load_config(dotenv=tmp_path / "none.env", overrides={"INFERENCE_BASE_URL": url, "OUT": str(tmp_path / "out"), "INFERENCE_MODEL": "mock-scout"})


FINAL = {
    "summary": "A small CSV export service.",
    "facts": [
        {"claim": "svc/export.py defines export_rows and Exporter", "evidence": ["E3"]},
        {"claim": "the string 'csv' appears in svc/export.py", "evidence": ["E4"]},
        {"claim": "made up file util/magic.py exists", "evidence": ["E42"]},
    ],
    "inferences": [{"claim": "Exporter.fmt is meant to become configurable", "basis": "class attribute with a single literal (E3)"}],
    "unknowns": ["whether any caller passes a non-CSV format today"],
    "risks": [{"risk": "changing export_rows signature breaks callers", "severity": "medium", "mitigation": "keep positional args"}],
    "affected": {"tests": ["tests/test_export.py"], "contracts": ["export_rows(rows, path)"]},
    "plan": [{"step": "add a --json flag", "files": ["svc/export.py"], "rationale": "task", "risk": "low"}],
    "verification": [{"check": "unit tests", "command": "python -m pytest -q", "expected": "all pass"}],
    "next_actions": ["confirm callers of export_rows"],
    "stop_reason": None,
}


def test_end_to_end_fixture_repo(fixture_repo, tmp_path):
    root, sha = fixture_repo
    before = _snapshot(root)
    out_dir = tmp_path / "scout-out"
    srv, handler = _sequenced_server([
        (200, _tool_call("read_file", {"path": "svc/export.py"})),
        (200, _tool_call("search_text", {"pattern": "csv"})),
        (200, _tool_call("read_file", {"path": "../outside.txt"})),      # rejected by the sandbox, run continues
        (200, _tool_call("read_file", {"path": ".env"})),                # secrets refused
        (200, _tool_call("run_check", {"name": "tests"})),               # not offered -> unknown skill
        (200, _final("```json\n" + json.dumps(FINAL) + "\n```")),
    ])
    with _running(srv) as url:
        cfg = _cfg(url, tmp_path)
        result = run_scout(ScoutInputs(repo=root, task="Add a --json flag to the export command", out_dir=out_dir), cfg, LLM(cfg, retries=0))
    assert result.parsed and handler.calls == 6
    assert sorted(p.name for p in result.artifacts) == sorted(ARTIFACTS)
    assert _snapshot(root) == before, "fixture repo must be untouched"
    assert not (root / "scout-out").exists()

    doc = json.loads((out_dir / "evidence.json").read_text(encoding="utf-8"))
    assert validate_evidence_document(doc) == []
    meta = doc["metadata"]
    assert meta["git_sha"] == sha and meta["model"] == "mock-scout" and meta["prompt_version"] == "v1"
    assert meta["task"] == "Add a --json flag to the export command" and meta["runtime"].startswith("http://127.0.0.1:")
    tools = [c["tool"] for c in meta["tool_calls"]]
    assert tools == ["list_files", "git_log", "read_file", "search_text"]  # seeds, then the two allowed calls only
    e3 = next(e for e in doc["evidence"] if e["id"] == "E3")
    assert e3["path"] == "svc/export.py" and e3["symbols"] == ["export_rows", "Exporter"] and e3["sha"] == sha
    report = doc["report"]
    assert [f["claim"] for f in report["facts"]] == [FINAL["facts"][0]["claim"], FINAL["facts"][1]["claim"]]
    assert report["demoted"] == ["made up file util/magic.py exists"]
    assert report["unknowns"] == ["whether any caller passes a non-CSV format today"]

    pm = (out_dir / "project-map.md").read_text(encoding="utf-8")
    assert "svc/export.py defines export_rows and Exporter — evidence: E3" in pm
    assert "## Inferences" in pm and "Exporter.fmt is meant to become configurable" in pm
    assert "made up file util/magic.py exists" in pm.split("## Inferences")[1].split("## Unknowns")[0]
    assert sha in pm and "hunter2" not in pm
    hand = (out_dir / "handoff.md").read_text(encoding="utf-8")
    assert "facts demoted to inferences for missing/invalid citations: 1" in hand
    transcript = (out_dir / "transcript.jsonl").read_text(encoding="utf-8")
    assert '"validation_failed"' in transcript and '"tool_failed"' in transcript and "hunter2" not in transcript


def test_dry_run_writes_artifacts_without_model(fixture_repo, tmp_path):
    root, sha = fixture_repo
    cfg = _cfg("http://127.0.0.1:9", tmp_path)
    result = run_scout(ScoutInputs(repo=root, task="t", out_dir=tmp_path / "dry", dry_run=True), cfg)
    assert not result.parsed and result.report["stop_reason"].startswith("dry run")
    doc = json.loads((tmp_path / "dry" / "evidence.json").read_text(encoding="utf-8"))
    assert doc["metadata"]["dry_run"] is True and doc["metadata"]["git_sha"] == sha
    assert [e["kind"] for e in doc["evidence"]] == ["inventory", "git"]
    assert "svc/export.py" in doc["evidence"][0]["excerpt"] and ".env" not in doc["evidence"][0]["excerpt"]


def test_unparseable_answer_still_writes_artifacts_and_exit_4(fixture_repo, tmp_path, monkeypatch):
    root, _ = fixture_repo
    srv, _ = _sequenced_server([(200, _final("I looked around and it seems fine."))])
    with _running(srv) as url:
        monkeypatch.setenv("INFERENCE_BASE_URL", url)
        monkeypatch.setenv("OUT", str(tmp_path / "out"))
        monkeypatch.chdir(tmp_path)
        rc = main(["--repo", str(root), "--task", "t", "--out", str(tmp_path / "bad")])
    assert rc == 4
    assert (tmp_path / "bad" / "raw-answer.txt").read_text(encoding="utf-8").startswith("I looked")
    assert (tmp_path / "bad" / "handoff.md").exists()


def test_sources_and_out_dir_rules(fixture_repo, tmp_path):
    root, _ = fixture_repo
    cfg = _cfg("http://127.0.0.1:9", tmp_path)
    with pytest.raises(SandboxError, match="inside the target repo"):
        run_scout(ScoutInputs(repo=root, task="t", out_dir=root / "out", dry_run=True), cfg)
    with pytest.raises(SandboxError, match="contain the target repo"):
        run_scout(ScoutInputs(repo=root, task="t", out_dir=tmp_path, dry_run=True), cfg)
    with pytest.raises(SandboxError, match="existing file"):
        run_scout(ScoutInputs(repo=root, task="t", out_dir=tmp_path / "o", sources=(tmp_path / "nope.md",), dry_run=True), cfg)
    notes = tmp_path / "notes.md"
    notes.write_text("acceptance: json output\n")
    r = run_scout(ScoutInputs(repo=root, task="t", out_dir=tmp_path / "o2", sources=(notes,), dry_run=True), cfg)
    doc = json.loads((r.out_dir / "evidence.json").read_text(encoding="utf-8"))
    assert doc["evidence"][0]["kind"] == "input" and doc["metadata"]["sources"][0]["name"] == "notes.md"


def test_cli_usage_errors(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["--repo", str(tmp_path)])
    assert main(["--repo", str(tmp_path / "missing"), "--task", "t", "--dry-run", "--out", str(tmp_path / "o")]) == 2
    assert main(["--repo", str(tmp_path), "--task-file", str(tmp_path / "no.md"), "--out", str(tmp_path / "o")]) == 2
