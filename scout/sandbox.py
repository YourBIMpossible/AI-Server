"""The scout's only door into the target repo: every path is validated against one root,
every operation is bounded, nothing is ever written.

Rules (tests/test_scout_sandbox.py):
* a path argument is repo-relative; absolute paths, drive letters, `..` segments, NULs and
  anything that resolves (through symlinks) outside the root are rejected with SandboxError;
* `.git`, `.env*`, dependency/venv/build/output folders and binary files are never listed,
  read or searched;
* reads, listings, searches, git output and check output are all capped in bytes / count;
* git is invoked with fixed argv (never a shell) and a scrubbed environment;
* `run_check` runs only operator-named argv entries, `shell=False`, with a timeout.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", "out",
    "dist", "build", "vendor", "target", ".claude", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".idea", ".vscode", ".gradle", "bin", "obj", "packages",
})
DENIED_FILE_PREFIXES = (".env", "id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc")
DENIED_FILE_NAMES = frozenset({"credentials", "credentials.json", "secrets.json", "token.json"})
BINARY_EXT = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tgz",
    ".bz2", ".xz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyd", ".class",
    ".jar", ".whl", ".gguf", ".safetensors", ".bin", ".pt", ".pth", ".onnx", ".db", ".sqlite",
    ".sqlite3", ".rvt", ".rfa", ".dwg", ".ifc", ".mp3", ".mp4", ".wav", ".mov", ".ttf", ".woff",
    ".woff2", ".eot", ".psd", ".ai", ".xlsx", ".docx", ".pptx", ".parquet",
})
_GIT_ENV_KEEP = ("PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "TEMP", "TMP", "LANG", "LC_ALL", "PROGRAMDATA")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^-]{0,63}$")


class SandboxError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_read_bytes: int = 64 * 1024
    max_files: int = 5000
    max_list: int = 500
    max_search_hits: int = 200
    max_search_file_bytes: int = 1024 * 1024
    max_result_bytes: int = 16 * 1024
    git_timeout_s: float = 30.0
    check_timeout_s: float = 120.0
    max_check_output: int = 16 * 1024
    run_budget_s: float = 30 * 60


@dataclass(frozen=True)
class FileInfo:
    path: str   # posix, repo-relative
    size: int


@dataclass
class Sandbox:
    root: Path
    limits: Limits = field(default_factory=Limits)
    checks: dict[str, list[str]] = field(default_factory=dict)
    _started: float = field(default_factory=time.monotonic, init=False, repr=False)

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not root.is_dir():
            raise SandboxError(f"target repo is not a directory: {root}")
        self.root = root.resolve(strict=True)

    # -- time budget ---------------------------------------------------------
    def check_budget(self) -> None:
        if time.monotonic() - self._started > self.limits.run_budget_s:
            raise SandboxError("run time budget exhausted; finish with what you have")

    # -- path validation -----------------------------------------------------
    def resolve(self, rel: str, *, must_exist: bool = True) -> Path:
        """Repo-relative string -> real path inside root, or SandboxError."""
        if not isinstance(rel, str):
            raise SandboxError("path must be a string")
        if "\x00" in rel:
            raise SandboxError("path contains NUL")
        s = rel.strip()
        if s in ("", "."):
            return self.root
        if s.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", s) or Path(s).is_absolute():
            raise SandboxError(f"absolute paths are not allowed: {rel!r}")
        parts = [p for p in re.split(r"[\\/]+", s) if p not in ("", ".")]
        if ".." in parts:
            raise SandboxError(f"parent traversal is not allowed: {rel!r}")
        candidate = self.root.joinpath(*parts)
        real = candidate.resolve(strict=False)
        try:
            real.relative_to(self.root)
        except ValueError:
            raise SandboxError(f"path escapes the target repo (symlink?): {rel!r}") from None
        if must_exist and not real.exists():
            raise SandboxError(f"no such path in target repo: {rel!r}")
        return real

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def is_denied(self, rel_posix: str) -> bool:
        parts = rel_posix.split("/")
        if any(p in IGNORED_DIRS for p in parts[:-1]):
            return True
        name = parts[-1]
        low = name.lower()
        if low.startswith(DENIED_FILE_PREFIXES) or low in DENIED_FILE_NAMES:
            return True
        return Path(name).suffix.lower() in BINARY_EXT

    # -- inventory -----------------------------------------------------------
    def inventory(self, subdir: str = "", *, max_files: int | None = None) -> tuple[list[FileInfo], bool]:
        """Sorted (path, size) list of allowed files under subdir; (files, truncated)."""
        self.check_budget()
        cap = min(max_files or self.limits.max_files, self.limits.max_files)
        base = self.resolve(subdir)
        if not base.is_dir():
            raise SandboxError(f"not a directory: {subdir!r}")
        rels = self._git_ls_files(base)
        if rels is None:
            rels = self._walk(base)
        out: list[FileInfo] = []
        for r in sorted(set(rels)):
            if self.is_denied(r):
                continue
            p = self.root / r
            try:
                if p.is_symlink() or not p.is_file():
                    continue
                size = p.stat().st_size
            except OSError:
                continue
            out.append(FileInfo(r, size))
            if len(out) >= cap:
                return out, True
        return out, False

    def _git_ls_files(self, base: Path) -> list[str] | None:
        if not (self.root / ".git").exists():
            return None
        try:
            raw = self._git(["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", str(base)], text=False)
        except SandboxError:
            return None
        return [x.decode("utf-8", "replace").replace("\\", "/") for x in raw.split(b"\0") if x]

    def _walk(self, base: Path) -> list[str]:
        rels: list[str] = []
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not (Path(dirpath) / d).is_symlink())
            for f in filenames:
                rels.append((Path(dirpath) / f).relative_to(self.root).as_posix())
                if len(rels) > self.limits.max_files * 2:
                    return rels
        return rels

    # -- reading -------------------------------------------------------------
    def read_text(self, rel: str, *, start_line: int = 1, end_line: int | None = None) -> tuple[str, int, bool]:
        """(text of [start_line, end_line], total_lines_seen, truncated_by_bytes)."""
        self.check_budget()
        path = self.resolve(rel)
        rp = self.rel(path)
        if self.is_denied(rp):
            raise SandboxError(f"path is excluded from reading: {rel!r}")
        if not path.is_file():
            raise SandboxError(f"not a file: {rel!r}")
        if start_line < 1 or (end_line is not None and end_line < start_line):
            raise SandboxError("invalid line range")
        with path.open("rb") as fh:
            data = fh.read(self.limits.max_read_bytes + 1)
        if b"\x00" in data[:8192]:
            raise SandboxError(f"binary file: {rel!r}")
        truncated = len(data) > self.limits.max_read_bytes
        text = data[: self.limits.max_read_bytes].decode("utf-8", "replace")
        lines = text.splitlines()
        stop = len(lines) if end_line is None else min(end_line, len(lines))
        return "\n".join(lines[start_line - 1: stop]), len(lines), truncated

    # -- search --------------------------------------------------------------
    def search(self, pattern: str, *, subdir: str = "", regex: bool = False, max_hits: int | None = None) -> tuple[list[tuple[str, int, str]], bool]:
        """[(path, lineno, line)] sorted by path then line; (hits, truncated)."""
        self.check_budget()
        if not pattern or len(pattern) > 200:
            raise SandboxError("pattern must be 1-200 characters")
        if regex:
            try:
                rx = re.compile(pattern)
            except re.error as e:
                raise SandboxError(f"bad regex: {e}") from None
            match = rx.search
        else:
            match = lambda line: pattern in line  # noqa: E731
        cap = min(max_hits or self.limits.max_search_hits, self.limits.max_search_hits)
        files, _ = self.inventory(subdir)
        hits: list[tuple[str, int, str]] = []
        for fi in files:
            if fi.size > self.limits.max_search_file_bytes:
                continue
            try:
                with (self.root / fi.path).open("rb") as fh:
                    head = fh.read(8192)
                    if b"\x00" in head:
                        continue
                    data = head + fh.read()
            except OSError:
                continue
            for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if match(line):
                    hits.append((fi.path, n, line.rstrip()[:300]))
                    if len(hits) >= cap:
                        return hits, True
        return hits, False

    # -- git -----------------------------------------------------------------
    def _git(self, args: list[str], *, text: bool = True):
        env = {k: os.environ[k] for k in _GIT_ENV_KEEP if k in os.environ}
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.root), *args], capture_output=True, text=text,
                timeout=self.limits.git_timeout_s, env=env, check=False, shell=False,
            )
        except FileNotFoundError:
            raise SandboxError("git is not installed") from None
        except subprocess.TimeoutExpired:
            raise SandboxError("git timed out") from None
        if proc.returncode != 0:
            err = proc.stderr if text else proc.stderr.decode("utf-8", "replace")
            raise SandboxError(f"git {args[0]} failed: {err.strip()[:300]}")
        return proc.stdout

    def is_git_repo(self) -> bool:
        return (self.root / ".git").exists()

    def head_sha(self) -> str | None:
        if not self.is_git_repo():
            return None
        try:
            return self._git(["rev-parse", "HEAD"]).strip() or None
        except SandboxError:
            return None

    def git_status(self) -> str:
        self.check_budget()
        return self._cap(self._git(["status", "--porcelain=v1", "--branch", "--untracked-files=normal"]))

    def git_log(self, *, max_count: int = 20, path: str | None = None) -> str:
        self.check_budget()
        n = max(1, min(int(max_count), 200))
        args = ["log", "--no-decorate", "--date=short", f"--format=%h %ad %s", f"-n{n}", "--no-color"]
        if path:
            args += ["--", self.rel(self.resolve(path))]
        return self._cap(self._git(args))

    def git_diff(self, *, base: str | None = None, path: str | None = None, staged: bool = False) -> str:
        self.check_budget()
        args = ["diff", "--no-color", "--no-ext-diff", "--stat=120", "-p"]
        if staged:
            args.append("--cached")
        if base is not None:
            if not _REF_RE.match(base):
                raise SandboxError(f"invalid git ref: {base!r}")
            args.append(base)
        args.append("--")
        if path:
            args.append(self.rel(self.resolve(path)))
        return self._cap(self._git(args))

    # -- allowlisted checks --------------------------------------------------
    def run_check(self, name: str) -> tuple[int, str, bool]:
        """Run one operator-named argv (never a shell string) inside the repo; (rc, output, truncated)."""
        self.check_budget()
        argv = self.checks.get(name)
        if not argv:
            known = ", ".join(sorted(self.checks)) or "(none)"
            raise SandboxError(f"unknown check {name!r}; allowed: {known}")
        env = {k: os.environ[k] for k in _GIT_ENV_KEEP if k in os.environ}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            proc = subprocess.run(
                argv, cwd=str(self.root), capture_output=True, text=True, env=env, shell=False,
                timeout=self.limits.check_timeout_s, check=False,
            )
        except FileNotFoundError:
            raise SandboxError(f"check {name!r}: executable not found: {argv[0]!r}") from None
        except subprocess.TimeoutExpired:
            raise SandboxError(f"check {name!r} timed out after {self.limits.check_timeout_s:.0f}s") from None
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        truncated = len(out) > self.limits.max_check_output
        return proc.returncode, out[: self.limits.max_check_output], truncated

    # -- helpers -------------------------------------------------------------
    def _cap(self, text: str) -> str:
        if len(text) <= self.limits.max_result_bytes:
            return text
        return text[: self.limits.max_result_bytes] + f"\n... [truncated at {self.limits.max_result_bytes} bytes]"


def parse_checks(specs: Iterable[str]) -> dict[str, list[str]]:
    """'NAME=prog arg arg' -> {NAME: [prog, arg, arg]}; split with shlex, no shell features."""
    import shlex

    out: dict[str, list[str]] = {}
    for spec in specs:
        name, sep, cmd = spec.partition("=")
        name = name.strip()
        if not sep or not re.match(r"^[A-Za-z0-9_-]{1,40}$", name):
            raise SandboxError(f"check spec must be NAME=command: {spec!r}")
        if sys.platform == "win32":
            # non-posix mode keeps backslash paths intact but leaves the quotes on quoted tokens
            argv = [t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t for t in shlex.split(cmd, posix=False)]
        else:
            argv = shlex.split(cmd)
        if not argv:
            raise SandboxError(f"check {name!r} has an empty command")
        out[name] = argv
    return out
