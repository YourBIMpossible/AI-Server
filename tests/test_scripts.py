"""WP-A: the refactored scripts use `aiserver` and behave correctly against the mock endpoint."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_test_ok_against_mock(mock_endpoint, monkeypatch, capsys):
    monkeypatch.setenv("OLLAMA_HOST", mock_endpoint)
    mod = _load("smoke_test", "scripts/smoke-test.py")
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "model said: ok" in out  # mock chat content


def test_daily_digest_writes_digest(mock_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    buildlog = ws / "BIMpossible_Workspace" / "01_BuildLog"
    declog = ws / "AI-Brain-Data" / "decision-log"
    buildlog.mkdir(parents=True)
    declog.mkdir(parents=True)
    (buildlog / "2026-06-16__demo.md").write_text("did a thing", encoding="utf-8")
    (declog / "2026-06-16.md").write_text("decided a thing", encoding="utf-8")

    out = tmp_path / "out"
    monkeypatch.setenv("WORKSPACE", str(ws))
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("OLLAMA_HOST", mock_endpoint)
    monkeypatch.setenv("DIGEST_DAYS", "7")

    mod = _load("daily_digest", "automation/daily_digest.py")
    assert mod.main() == 0

    digests = list(out.glob("digest-*.md"))
    assert len(digests) == 1
    body = digests[0].read_text(encoding="utf-8")
    assert "# Daily digest" in body
    assert "## Sources" in body
    assert "2026-06-16__demo.md" in body
    assert "2026-06-16.md" in body
    assert "ok" in body  # mock chat summary


def test_daily_digest_no_activity(mock_endpoint, tmp_path, monkeypatch):
    ws = tmp_path / "empty-ws"
    ws.mkdir()
    out = tmp_path / "out"
    monkeypatch.setenv("WORKSPACE", str(ws))
    monkeypatch.setenv("OUT", str(out))
    monkeypatch.setenv("OLLAMA_HOST", mock_endpoint)

    mod = _load("daily_digest", "automation/daily_digest.py")
    assert mod.main() == 0
    digests = list(out.glob("digest-*.md"))
    assert len(digests) == 1
    assert "No build-log or decision-log activity" in digests[0].read_text(encoding="utf-8")
