"""WP-D3: the local-LLM Revit weekly-summary job (side-by-side with the deterministic one)."""
import automation.revit_weekly  # noqa: F401  (registers the job)
from automation._framework import job_names, run_job


def _seed(ws):
    ds = ws / "AI-Brain-Data" / "Revit-AI" / "daily-summaries"
    ds.mkdir(parents=True)
    (ds / "2026-06-11-summary.md").write_text(
        "# Daily Summary: 2026-06-11\n\n**Sessions:** 6\n\n## Counts\n- Saves: 22\n- Errors: 5\n",
        encoding="utf-8",
    )
    (ds / "2026-06-12-summary.md").write_text(
        "# Daily Summary: 2026-06-12\n\n**Sessions:** 2\n\n## Counts\n- Saves: 8\n- Errors: 1\n",
        encoding="utf-8",
    )
    return ds


def _env(monkeypatch, ws, out, host):
    monkeypatch.setenv("WORKSPACE", str(ws))
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("OLLAMA_HOST", host)


def test_revit_weekly_is_registered():
    assert "revit-weekly" in job_names()


def test_revit_weekly_writes_local_summary(mock_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    _seed(ws)
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)

    path = run_job("revit-weekly")
    assert path.exists()
    assert path.parent == out / "revit-weekly"
    body = path.read_text(encoding="utf-8")
    assert "# Revit weekly" in body
    assert "2026-06-12-summary.md" in body   # source days listed
    assert "ok" in body                       # mock chat summary


def test_revit_weekly_no_activity(mock_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "empty"
    ws.mkdir()
    out = tmp_path / "out"
    _env(monkeypatch, ws, out, mock_endpoint)
    path = run_job("revit-weekly")
    assert "No Revit daily-summaries" in path.read_text(encoding="utf-8")
