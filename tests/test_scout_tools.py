"""scout/tools.py: every skill is read-only, records evidence, and is rejected outside its scope."""
import os
import subprocess

import pytest

from harness.policy import AllowlistReadOnly
from harness.registry import REGISTRY, validate_args, ValidationError
from scout.evidence import EvidenceLog
from scout.sandbox import Sandbox, SandboxError, parse_checks
from scout.tools import SCOUT_SKILLS, skills_for


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app" / "svc.py").write_text("class Service:\n    def handle(self):\n        return 1\n")
    (root / "README.md").write_text("service repo\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "first"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)
    return root


def _skill(name, sb):
    ev = EvidenceLog(sha=sb.head_sha())
    return SCOUT_SKILLS[name](None, sandbox=sb, evidence=ev), ev


def test_scout_skills_are_not_in_the_harness_registry():
    assert not set(SCOUT_SKILLS) & set(REGISTRY)
    assert "knowledge" not in SCOUT_SKILLS
    for cls in SCOUT_SKILLS.values():
        assert cls.name and cls.description and cls.schema.get("type") == "object"


def test_skills_for_hides_checks_and_git_when_unavailable(repo, tmp_path):
    assert "run_check" not in skills_for(Sandbox(repo))
    assert "git_status" in skills_for(Sandbox(repo))
    plain = tmp_path / "plain"
    plain.mkdir()
    names = set(skills_for(Sandbox(plain, checks={"x": ["true"]})))
    assert "run_check" in names and not {"git_status", "git_log", "git_diff"} & names


def test_allowlist_policy_admits_only_scout_skills(repo):
    policy = AllowlistReadOnly(SCOUT_SKILLS)
    skill, _ = _skill("read_file", Sandbox(repo))
    assert policy.may_auto_run(skill, {"path": "README.md"})

    class Other:
        name = "shell"

    assert not policy.may_auto_run(Other(), {})


def test_read_file_records_evidence_with_lines_symbols_and_sha(repo):
    sb = Sandbox(repo)
    skill, ev = _skill("read_file", sb)
    res = skill.run(path="app/svc.py", start_line=1, end_line=2)
    assert res.content.startswith("[E1] app/svc.py lines 1-2 of 3\n1: class Service:")
    e = ev.items[0]
    assert e.kind == "file" and e.path == "app/svc.py" and e.lines == [1, 2]
    assert e.symbols == ["Service", "handle"] and e.sha == sb.head_sha()
    assert ev.tool_calls == [{"evidence_id": "E1", "tool": "read_file", "args": {"end_line": 2, "path": "app/svc.py", "start_line": 1}}]


def test_read_file_outside_repo_raises(repo, tmp_path):
    (tmp_path / "secret.txt").write_text("x")
    skill, ev = _skill("read_file", Sandbox(repo))
    with pytest.raises(SandboxError):
        skill.run(path="../secret.txt")
    with pytest.raises(SandboxError):
        skill.run(path=str(tmp_path / "secret.txt"))
    assert ev.items == []


def test_list_and_search_and_git_tools(repo):
    sb = Sandbox(repo)
    out = SCOUT_SKILLS["list_files"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run()
    assert "[E1] " in out.content and "app/svc.py\t" in out.content
    out = SCOUT_SKILLS["search_text"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run(pattern="Service")
    assert "app/svc.py:1: class Service:" in out.content and out.metadata["count"] == 1
    out = SCOUT_SKILLS["git_log"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run(max_count=1)
    assert "first" in out.content
    out = SCOUT_SKILLS["git_status"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run()
    assert out.content.startswith("[E1] ##")
    out = SCOUT_SKILLS["git_diff"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run()
    assert "(no differences)" in out.content


def test_run_check_only_named_allowlist_and_records_argv(repo):
    import sys

    checks = parse_checks([f"ver={sys.executable} --version"])
    sb = Sandbox(repo, checks=checks)
    skill, ev = _skill("run_check", sb)
    res = skill.run(name="ver")
    assert res.metadata["exit_code"] == 0 and "Python" in res.content
    assert ev.items[0].args["argv"] == checks["ver"]
    with pytest.raises(SandboxError):
        skill.run(name="rm -rf /")


def test_schemas_reject_wrong_types():
    with pytest.raises(ValidationError):
        validate_args(SCOUT_SKILLS["read_file"].schema, {})
    with pytest.raises(ValidationError):
        validate_args(SCOUT_SKILLS["search_text"].schema, {"pattern": 3})
    validate_args(SCOUT_SKILLS["list_files"].schema, {"subdir": "app", "max_files": 5})


def test_tools_never_write_into_target(repo):
    before = {p: p.stat().st_mtime_ns for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    sb = Sandbox(repo)
    for name in ("list_files", "git_status", "git_log", "git_diff"):
        SCOUT_SKILLS[name](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run()
    SCOUT_SKILLS["search_text"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run(pattern="x")
    SCOUT_SKILLS["read_file"](None, sandbox=sb, evidence=EvidenceLog(sha=None)).run(path="README.md")
    after = {p: p.stat().st_mtime_ns for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert before == after
