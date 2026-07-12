"""WP-C: job framework + the three jobs run against a mock endpoint and write files under out/."""
import subprocess
import sys
from pathlib import Path

import pytest

from aiserver import LLM, load_config

REPO = Path(__file__).resolve().parent.parent

# importing the job modules registers them (the CLI dispatcher does the same)
import automation.daily_digest  # noqa: F401
import automation.decision_drift  # noqa: F401
import automation.weekly_rollup  # noqa: F401
from automation._framework import REGISTRY, Job, JobPreconditionError, job_names, register, run_job


def _seed_workspace(ws):
    bl = ws / "BIMpossible_Workspace" / "01_BuildLog"
    dl = ws / "AI-Brain-Data" / "decision-log"
    bl.mkdir(parents=True)
    dl.mkdir(parents=True)
    (bl / "2026-06-16__demo.md").write_text("shipped the job framework", encoding="utf-8")
    (dl / "2026-06-16.md").write_text("decided to use sqlite-vec", encoding="utf-8")
    return bl, dl


def _env(monkeypatch, ws, out, host):
    monkeypatch.setenv("WORKSPACE", str(ws))
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("OLLAMA_HOST", host)
    monkeypatch.setenv("DIGEST_DAYS", "7")


def test_registry_contains_the_three_jobs():
    assert {"daily-digest", "decision-drift", "weekly-rollup"}.issubset(job_names())


def test_unknown_job_raises():
    with pytest.raises(KeyError):
        run_job("does-not-exist")


def test_daily_digest_job_writes_to_out_root(mock_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _seed_workspace(ws)
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)

    path = run_job("daily-digest")
    assert path.exists()
    assert path.parent == out  # behaviour unchanged: digest stays in out/ root
    body = path.read_text(encoding="utf-8")
    assert "# Daily digest" in body
    assert "## Sources" in body
    assert "2026-06-16__demo.md" in body


def test_daily_digest_no_activity(mock_endpoint, tmp_path, monkeypatch):
    # Source roots exist but have zero recent files -- a genuinely quiet period,
    # distinct from AUTO-6's "roots don't exist at all" case tested below.
    ws = tmp_path / "ws"
    (ws / "BIMpossible_Workspace" / "01_BuildLog").mkdir(parents=True)
    (ws / "AI-Brain-Data" / "decision-log").mkdir(parents=True)
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)
    path = run_job("daily-digest")
    assert "No build-log or decision-log activity" in path.read_text(encoding="utf-8")


def test_daily_digest_reports_missing_workspace_roots_distinctly_from_no_activity(
    mock_endpoint, tmp_path, monkeypatch
):
    # AUTO-6: neither source directory existing at all (e.g. WORKSPACE misconfigured
    # after relocation) used to read identically to a genuinely quiet week -- this is
    # the exact scenario the old version of test_daily_digest_no_activity above
    # exercised without realizing its fixture was actually the misconfiguration case.
    ws = tmp_path / "empty"
    ws.mkdir()
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)
    path = run_job("daily-digest")
    body = path.read_text(encoding="utf-8")
    assert "WORKSPACE roots not found" in body
    assert "No build-log or decision-log activity" not in body


def test_weekly_rollup_reports_missing_workspace_roots(mock_endpoint, tmp_path, monkeypatch):
    # Same AUTO-6 fix applied to weekly_rollup.py, which shares collect_logs.
    ws = tmp_path / "empty"
    ws.mkdir()
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)
    path = run_job("weekly-rollup")
    assert "WORKSPACE roots not found" in path.read_text(encoding="utf-8")


def test_weekly_rollup_job_writes_under_its_subdir(mock_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _seed_workspace(ws)
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)

    path = run_job("weekly-rollup")
    assert path.exists()
    assert path.parent == out / "weekly-rollup"
    assert "# Weekly rollup" in path.read_text(encoding="utf-8")


def test_decision_drift_job_writes_report(embed_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _seed_workspace(ws)
    (ws / "BIMpossible_Workspace" / "01_BuildLog" / "standards.md").write_text(
        "sqlite-vec vector store decision rationale", encoding="utf-8"
    )
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, embed_endpoint)

    # drift reads the index; build it first over the canonical (BuildLog) docs
    from rag.ingest import ingest
    from rag.store import VectorStore

    cfg = load_config()
    store = VectorStore(cfg.out / "rag" / "index.db")
    ingest([ws / "BIMpossible_Workspace"], store, LLM(cfg).embed)
    store.close()

    path = run_job("decision-drift")
    assert path.exists()
    assert path.name.startswith("drift-")
    assert path.parent == out / "rag"  # thin wrapper -> same location as rag.drift


def test_decision_drift_raises_when_decision_log_missing(mock_endpoint, tmp_path, monkeypatch):
    # AUTO-2: a missing decision-log must fail loud, not silently report "0 of 0
    # decisions" (which reads as "all clear").
    ws = tmp_path / "ws"
    (ws / "BIMpossible_Workspace" / "01_BuildLog").mkdir(parents=True)
    # deliberately do NOT create ws/AI-Brain-Data/decision-log
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)
    with pytest.raises(JobPreconditionError):
        run_job("decision-drift")


def test_decision_drift_banners_an_empty_index(embed_endpoint, tmp_path, monkeypatch):
    # AUTO-2: a never-ingested index must not silently flag every decision as
    # "undocumented" without saying that's an artifact of an empty index.
    ws = tmp_path / "ws"
    _seed_workspace(ws)  # decision-log exists with an entry, but nothing was ever ingested
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, embed_endpoint)

    path = run_job("decision-drift")
    body = path.read_text(encoding="utf-8")
    assert "WARNING: the RAG index has no indexed documents" in body


def test_cli_list_lists_the_jobs():
    result = subprocess.run(
        [sys.executable, "-m", "automation", "list"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ("daily-digest", "decision-drift", "weekly-rollup"):
        assert name in result.stdout


def test_adding_a_new_job_is_one_subclass(tmp_path, monkeypatch):
    @register
    class _Demo(Job):
        name = "demo-job"
        schedule = "manual"

        def run(self):
            p = self.out_dir / "hello.md"
            p.write_text("hi", encoding="utf-8")
            return p

    monkeypatch.setenv("OUT", str(tmp_path / "out"))
    try:
        path = run_job("demo-job")
        assert path.exists()
        assert path.parent == tmp_path / "out" / "demo-job"
    finally:
        REGISTRY.pop("demo-job", None)
