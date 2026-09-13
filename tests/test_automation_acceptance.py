"""Task 4 acceptance runner: box workspace from git history, the real job, graded output."""
import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("automation_acceptance", REPO / "scripts" / "automation_acceptance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Judge:
    def __init__(self, verdict):
        self.verdict = verdict

    def chat(self, messages, **_):
        return self.verdict


def _repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "WP-E: add the API-key gateway")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "Merge pull request #1 from x")
    return r


def test_build_workspace_matches_the_job_layout_and_skips_merges(tmp_path):
    m = _load()
    ws = m.build_workspace(tmp_path / "ws", [("AI-Server", _repo(tmp_path), "HEAD")], "# Decision\nbody")
    logs = list((ws / "BIMpossible_Workspace" / "01_BuildLog").glob("*.md"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "[AI-Server] WP-E: add the API-key gateway" in text and "Merge pull request" not in text
    assert (ws / "AI-Brain-Data" / "decision-log" / "2026-09-13__box-phase0-remeasure.md").exists()


def test_the_real_job_reads_the_generated_workspace(tmp_path):
    from automation._framework import collect_logs

    m = _load()
    ws = m.build_workspace(tmp_path / "ws", [("AI-Server", _repo(tmp_path), "HEAD")], "# Decision\ncold-load gone")
    listed, corpus, found = collect_logs(ws, 7)
    assert found and len(listed) == 2 and "API-key gateway" in corpus and "cold-load gone" in corpus


def test_grade_judge_is_a_gate():
    m = _load()
    rubric = json.loads((REPO / "eval" / "automation_rubrics" / "daily-digest-box.json").read_text(encoding="utf-8"))["rubric"]
    good = "- Built the API key gateway\n- WP-F eval now separates models\n- WP-H bakeoff protocol frozen\n- Phase 0 re-measured"
    assert m.grade(good, rubric, judge_llm=_Judge("PASS"), judge_model="j", threshold=0.8)["passed"]
    assert not m.grade(good, rubric, judge_llm=_Judge("FAIL"), judge_model="j", threshold=0.8)["passed"]
    assert not m.grade("nothing relevant", rubric, judge_llm=_Judge("PASS"), judge_model="j", threshold=0.8)["passed"]


def test_end_to_end_against_the_stdlib_mock_fails_the_grade(mock_endpoint, tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "REPO", REPO)
    rc = m.main(["--label", "mock", "--base-url", mock_endpoint, "--model", "mock-model", "--out", str(tmp_path)])
    result = json.loads(next((tmp_path / "acceptance").glob("mock-*.json")).read_text(encoding="utf-8"))
    assert result["job_exit"] == 0 and result["digest_file"]  # the real job ran start to finish
    assert rc == 1 and result["accepted"] is False  # "ok" is not a digest
