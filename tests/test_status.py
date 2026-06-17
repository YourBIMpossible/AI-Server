"""WP-D1: the AI-Server status helper the Dashboard refresh runs locally."""
import importlib.util
import json
from pathlib import Path

from aiserver import load_config

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "aiserver_status", REPO / "scripts" / "aiserver_status.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cfg(tmp_path, host="http://127.0.0.1:1"):
    return load_config(
        dotenv=REPO / "no-such.env",
        overrides={"OUT": str(tmp_path / "out"), "OLLAMA_HOST": host},
    )


def _seed_out(tmp_path):
    out = tmp_path / "out"
    (out / "weekly-rollup").mkdir(parents=True)
    (out / "rag").mkdir(parents=True)
    (out / "digest-2026-06-16.md").write_text(
        "# Daily digest — 2026-06-16\n\n_Last 7 days · 3 files_\n\nbody\n", encoding="utf-8"
    )
    (out / "weekly-rollup" / "rollup-2026-06-15.md").write_text(
        "# Weekly rollup — 2026-06-15\n\nbody\n", encoding="utf-8"
    )
    (out / "rag" / "drift-2026-06-14.md").write_text(
        "# Decision drift — 2026-06-14\n\n_2 of 5 decisions ..._\n", encoding="utf-8"
    )
    return out


def test_job_outputs_reads_newest_of_each(tmp_path):
    mod = _load()
    jobs = mod.job_outputs(_seed_out(tmp_path))
    assert jobs["daily-digest"]["file"] == "digest-2026-06-16.md"
    assert "Daily digest" in jobs["daily-digest"]["summary"]
    assert jobs["weekly-rollup"]["file"] == "rollup-2026-06-15.md"
    assert jobs["decision-drift"]["file"] == "drift-2026-06-14.md"
    assert jobs["daily-digest"]["modified"]  # ISO timestamp present


def test_job_outputs_missing_are_none(tmp_path):
    mod = _load()
    out = tmp_path / "out"
    out.mkdir()
    jobs = mod.job_outputs(out)
    assert jobs == {"daily-digest": None, "weekly-rollup": None, "decision-drift": None}


def test_endpoint_status_down(tmp_path):
    mod = _load()
    st = mod.endpoint_status(_cfg(tmp_path), timeout=1)
    assert st["up"] is False
    assert st["models_available"] == []


def test_endpoint_status_up_against_mock(mock_endpoint, tmp_path):
    mod = _load()
    st = mod.endpoint_status(_cfg(tmp_path, host=mock_endpoint), timeout=3)
    assert st["up"] is True
    assert "mock-model" in st["models_available"]


def test_build_status_is_json_serializable(mock_endpoint, tmp_path):
    mod = _load()
    _seed_out(tmp_path)
    status = mod.build_status(_cfg(tmp_path, host=mock_endpoint))
    json.dumps(status)  # must not raise
    assert status["endpoint"]["up"] is True
    assert status["jobs"]["daily-digest"]["file"] == "digest-2026-06-16.md"
    assert "generated" in status
