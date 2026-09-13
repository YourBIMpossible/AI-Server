"""scout/sandbox.py: path validation, scope enforcement, bounds, git wrappers, allowlisted checks."""
import os
import subprocess
import sys

import pytest

from scout.sandbox import Limits, Sandbox, SandboxError, parse_checks


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@x", "GIT_TERMINAL_PROMPT": "0"})


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("import os\n\n\ndef compute(x):\n    return x * 2\n\n\nclass Engine:\n    pass\n")
    (root / "README.md").write_text("# demo\nhello world\n")
    (root / ".env").write_text("SECRET=1\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.js").write_text("secret")
    (root / "img.png").write_bytes(b"\x89PNG\x00\x00")
    (root / ".gitignore").write_text("ignored.txt\n")
    (root / "ignored.txt").write_text("hello world ignored\n")
    (tmp_path / "outside.txt").write_text("outside\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_resolve_rejects_absolute_traversal_and_nul(repo, tmp_path):
    sb = Sandbox(repo)
    assert sb.resolve("pkg/core.py").name == "core.py"
    assert sb.resolve("pkg\\core.py").name == "core.py"
    assert sb.resolve("") == sb.root
    for bad in [str(tmp_path / "outside.txt"), "/etc/passwd", "C:\\Windows", "\\\\server\\share", "~/x",
                "../outside.txt", "pkg/../../outside.txt", "pkg/..\\..\\outside.txt", "a\x00b"]:
        with pytest.raises(SandboxError):
            sb.resolve(bad)
    with pytest.raises(SandboxError, match="no such path"):
        sb.resolve("pkg/missing.py")


def test_symlink_escape_is_rejected(repo, tmp_path):
    link = repo / "link.txt"
    dlink = repo / "dlink"
    try:
        os.symlink(tmp_path / "outside.txt", link)
        os.symlink(tmp_path, dlink, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")
    sb = Sandbox(repo)
    with pytest.raises(SandboxError, match="escapes"):
        sb.resolve("link.txt")
    with pytest.raises(SandboxError, match="escapes"):
        sb.resolve("dlink/outside.txt")
    paths = [f.path for f in sb.inventory()[0]]
    assert "link.txt" not in paths and not any(p.startswith("dlink/") for p in paths)


def test_inventory_filters_secrets_vendor_binary_and_gitignored(repo):
    files, truncated = Sandbox(repo).inventory()
    paths = [f.path for f in files]
    assert paths == sorted(paths)
    assert "pkg/core.py" in paths and "README.md" in paths
    for hidden in (".env", "node_modules/dep.js", "img.png", "ignored.txt"):
        assert hidden not in paths
    assert not truncated
    small, truncated = Sandbox(repo).inventory(max_files=1)
    assert len(small) == 1 and truncated


def test_inventory_without_git_uses_walk(tmp_path):
    root = tmp_path / "plain"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x")
    (root / "out").mkdir()
    (root / "out" / "junk.txt").write_text("x")
    sb = Sandbox(root)
    assert [f.path for f in sb.inventory()[0]] == ["src/a.py"]
    assert sb.head_sha() is None and not sb.is_git_repo()


def test_read_text_ranges_limits_and_denials(repo):
    sb = Sandbox(repo, limits=Limits(max_read_bytes=20))
    text, total, truncated = sb.read_text("README.md")
    assert truncated and total >= 1
    sb = Sandbox(repo)
    text, total, truncated = sb.read_text("pkg/core.py", start_line=4, end_line=5)
    assert text == "def compute(x):\n    return x * 2" and total == 9 and not truncated
    with pytest.raises(SandboxError, match="excluded"):
        sb.read_text(".env")
    with pytest.raises(SandboxError, match="excluded"):
        sb.read_text("node_modules/dep.js")
    with pytest.raises(SandboxError):
        sb.read_text("img.png")
    with pytest.raises(SandboxError, match="not a file"):
        sb.read_text("pkg")
    with pytest.raises(SandboxError, match="line range"):
        sb.read_text("README.md", start_line=5, end_line=2)


def test_search_substring_regex_and_caps(repo):
    sb = Sandbox(repo)
    hits, truncated = sb.search("hello world")
    assert hits == [("README.md", 2, "hello world")] and not truncated
    hits, _ = sb.search(r"^(def|class)\s", regex=True, subdir="pkg")
    assert [(p, n) for p, n, _ in hits] == [("pkg/core.py", 4), ("pkg/core.py", 8)]
    hits, truncated = sb.search("o", max_hits=1)
    assert len(hits) == 1 and truncated
    with pytest.raises(SandboxError, match="bad regex"):
        sb.search("(", regex=True)
    with pytest.raises(SandboxError):
        sb.search("")
    assert sb.search("SECRET")[0] == []  # .env never searched


def test_git_wrappers_are_bounded_and_validated(repo):
    sb = Sandbox(repo, limits=Limits(max_result_bytes=40))
    assert len(sb.head_sha()) == 40
    assert "## " in sb.git_status()
    log = Sandbox(repo).git_log(max_count=5)
    assert "init" in log
    (repo / "README.md").write_text("# demo\nchanged\n")
    diff = Sandbox(repo).git_diff(path="README.md")
    assert "+changed" in diff
    assert "truncated" in sb.git_diff()
    with pytest.raises(SandboxError, match="invalid git ref"):
        Sandbox(repo).git_diff(base="--output=/tmp/x")
    with pytest.raises(SandboxError):
        Sandbox(repo).git_log(path="../outside.txt")


def test_run_check_allowlist_only(repo):
    checks = parse_checks([f"py={sys.executable} -c \"import sys; print('ok'); sys.exit(3)\""])
    sb = Sandbox(repo, checks=checks)
    rc, out, truncated = sb.run_check("py")
    assert rc == 3 and "ok" in out and not truncated
    with pytest.raises(SandboxError, match="unknown check"):
        sb.run_check("rm")
    with pytest.raises(SandboxError, match="unknown check"):
        Sandbox(repo).run_check("py")
    with pytest.raises(SandboxError, match="timed out"):
        Sandbox(repo, checks=parse_checks([f"slow={sys.executable} -c \"import time; time.sleep(5)\""]),
                limits=Limits(check_timeout_s=0.5)).run_check("slow")
    for bad in ["noequals", "bad name=x", "empty="]:
        with pytest.raises(SandboxError):
            parse_checks([bad])


def test_budget_exhaustion_stops_tools(repo):
    sb = Sandbox(repo, limits=Limits(run_budget_s=0))
    sb._started -= 1
    with pytest.raises(SandboxError, match="budget"):
        sb.inventory()


def test_sandbox_requires_directory(tmp_path):
    with pytest.raises(SandboxError):
        Sandbox(tmp_path / "missing")
