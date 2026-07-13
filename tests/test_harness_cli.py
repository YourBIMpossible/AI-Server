"""harness/cli.py: `python -m harness "task"` entry point."""
from harness.cli import main


def test_cli_requires_a_task_argument(capsys):
    rc = main([])
    assert rc == 1
    assert "Usage" in capsys.readouterr().err


def test_cli_runs_and_prints_final_answer(tmp_path, monkeypatch, mock_endpoint, capsys):
    monkeypatch.setenv("OUT", str(tmp_path / "out"))
    monkeypatch.setenv("OLLAMA_HOST", mock_endpoint)
    rc = main(["what", "is", "2+2"])
    assert rc == 0
    assert "ok" in capsys.readouterr().out
