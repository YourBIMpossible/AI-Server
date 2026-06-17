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
from automation._framework import REGISTRY, Job, job_names, register, run_job


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
    ws = tmp_path / "empty"
    ws.mkdir()
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)
    path = run_job("daily-digest")
    assert "No build-log or decision-log activity" in path.read_text(encoding="utf-8")


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
