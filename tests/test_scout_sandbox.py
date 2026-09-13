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


def test_hostile_repo_config_cannot_run_external_command(repo, tmp_path):
    # The target repo is untrusted. Its own .git/config must never make an inspection command
    # execute code -- git's command-valued keys (diff.external, core.fsmonitor, core.pager,
    # core.sshCommand, credential.helper, ext:: protocol) are all neutralised by _GIT_HARDENING.
    sentinel = tmp_path / "pwned.txt"
    driver = tmp_path / "driver.py"
    driver.write_text(f"open({str(sentinel)!r}, 'w').close()\n")
    py = sys.executable.replace("\\", "/")
    drv = str(driver).replace("\\", "/")
    payload = f'"{py}" "{drv}"'  # forward slashes + quotes so git's shell runs it verbatim
    (repo / "README.md").write_text("# demo\nchanged\n")

    # Positive control: a RAW diff that honours the repo's diff.external DOES run the driver,
    # proving the planted config is a genuinely live command-execution vector.
    _git(repo, "config", "diff.external", payload)
    subprocess.run(["git", "-C", str(repo), "diff", "--ext-diff"], capture_output=True,
                   env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if not sentinel.exists():
        pytest.skip("this git build does not run diff.external as configured; control vacuous")
    sentinel.unlink()

    # Now plant every command-valued key and prove the sandbox fires NONE of them, across every
    # git wrapper it exposes (rev-parse, status, log, diff, path-scoped diff).
    for key in ("core.fsmonitor", "core.pager", "core.sshCommand", "credential.helper"):
        _git(repo, "config", key, payload)
    sb = Sandbox(repo)
    sb.head_sha()
    sb.git_status()
    sb.git_log()
    sb.git_diff()
    sb.git_diff(path="README.md")
    assert not sentinel.exists(), "a hardened git wrapper executed a repo-config command"


def test_git_diff_never_leaks_denied_file_contents(repo):
    # Denied files (secrets/keys) tracked alongside allowed source: the diff shows allowed
    # content in full and denied content never -- not as hunks, not as headers, not anywhere.
    for name, before in (("id_rsa", "KEY-BEFORE\n"), ("credentials.json", '{"s":"BEFORE"}\n'),
                         ("app with space.py", "v = 'SPACE-BEFORE'\n")):
        (repo / name).write_text(before)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add secrets + source")

    (repo / "id_rsa").write_text("KEY-LEAKED-XYZ\n")
    (repo / "credentials.json").write_text('{"s":"LEAKED-XYZ"}\n')
    (repo / ".env").write_text("SECRET=LEAKED-XYZ\n")  # tracked from the base fixture
    (repo / "pkg" / "core.py").write_text("def compute(x):\n    return x * 3  # ALLOWED-MARKER\n")
    (repo / "app with space.py").write_text("v = 'SPACE-ALLOWED-MARKER'\n")

    diff = Sandbox(repo).git_diff()
    assert "ALLOWED-MARKER" in diff                 # allowed source content is preserved
    assert "SPACE-ALLOWED-MARKER" in diff           # filename with a space is handled correctly
    for leaked in ("LEAKED-XYZ", "KEY-LEAKED"):
        assert leaked not in diff                   # no denied content anywhere in the patch
    for denied_name in ("id_rsa", "credentials.json", ".env"):
        assert denied_name not in diff              # not even as a diff/stat header

    # A direct request for a denied path is refused rather than quietly returning its diff.
    for denied in (".env", "id_rsa", "credentials.json"):
        with pytest.raises(SandboxError, match="excluded"):
            Sandbox(repo).git_diff(path=denied)


def test_git_diff_rename_into_denied_name_is_excluded(repo):
    # A rename whose destination is a denied name must drop BOTH endpoints, so content cannot be
    # surfaced under a denied path; an allowed<->allowed rename is still shown.
    (repo / "moveme.py").write_text("MOVED-SECRET-CONTENT\n")
    (repo / "keepme.py").write_text("KEEP-CONTENT\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add rename sources")
    _git(repo, "mv", "moveme.py", "id_rsa")      # allowed content renamed INTO a denied name
    _git(repo, "mv", "keepme.py", "renamed.py")  # allowed -> allowed rename

    diff = Sandbox(repo).git_diff(staged=True)
    assert "MOVED-SECRET-CONTENT" not in diff and "id_rsa" not in diff  # denied-dest rename dropped
    assert "renamed.py" in diff                                        # allowed rename still shown


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
