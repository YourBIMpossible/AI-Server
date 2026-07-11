"""WP-A: scripts/smoke-test.py uses `aiserver` and works against the mock endpoint.

(The daily digest moved onto the job framework in WP-C; it is covered by test_automation.py.)
"""
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


def test_docs_point_at_the_working_task_registration_script():
    """XC-1: the singular register-task-windows.ps1 has no working entry point in
    daily_digest.py (no __main__); onboarding docs must reference the plural script,
    which uses the tested `python -m automation <job>` path instead.
    """
    for doc in (REPO / "README.md", REPO / "relocate.md"):
        text = doc.read_text(encoding="utf-8")
        assert "register-task-windows.ps1" not in text, f"{doc} still references the broken script"
    assert (REPO / "automation" / "register-tasks-windows.ps1").exists()
    assert not (REPO / "automation" / "register-task-windows.ps1").exists()
