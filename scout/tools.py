"""The skills the scout model may call. Each one is a thin wrapper over one Sandbox method,
records an Evidence entry, and prefixes its result with the evidence id so the model can cite
it. None of them takes a shell string, a path outside the target, or a write.

Not registered in harness.REGISTRY on purpose: `python -m harness` must not grow these, and
the scout must not see `knowledge` (it reads the personal RAG index, outside the target repo).
"""
from __future__ import annotations

from harness.registry import Skill, SkillResult

from .evidence import EvidenceLog, extract_symbols
from .sandbox import Sandbox, SandboxError


class ScoutSkill(Skill):
    def __init__(self, llm, *, sandbox: Sandbox, evidence: EvidenceLog):
        super().__init__(llm)
        self.sb = sandbox
        self.ev = evidence

    def _result(self, ev, body: str, **meta) -> SkillResult:
        return SkillResult(content=f"[{ev.id}] {body}", metadata={"evidence_id": ev.id, **meta})


class GitStatus(ScoutSkill):
    name = "git_status"
    description = "Working-tree status of the target repo (branch, modified/untracked files). Read-only."
    schema = {"type": "object", "properties": {}, "required": []}

    def run(self) -> SkillResult:
        out = self.sb.git_status()
        ev = self.ev.add(kind="git", tool=self.name, args={}, excerpt=out)
        return self._result(ev, out or "(clean)")


class GitLog(ScoutSkill):
    name = "git_log"
    description = "Recent commits (hash, date, subject), optionally limited to one path. Read-only."
    schema = {
        "type": "object",
        "properties": {
            "max_count": {"type": "integer", "description": "1-200, default 20"},
            "path": {"type": "string", "description": "repo-relative path to filter by"},
        },
        "required": [],
    }

    def run(self, *, max_count: int = 20, path: str | None = None) -> SkillResult:
        out = self.sb.git_log(max_count=max_count, path=path)
        ev = self.ev.add(kind="git", tool=self.name, args={"max_count": max_count, "path": path}, excerpt=out, path=path)
        return self._result(ev, out or "(no commits)")


class GitDiff(ScoutSkill):
    name = "git_diff"
    description = "Unified diff of the working tree (or the index with staged=true), optionally against a ref and/or limited to a path. Read-only."
    schema = {
        "type": "object",
        "properties": {
            "base": {"type": "string", "description": "git ref to diff against, e.g. HEAD~3 or main"},
            "path": {"type": "string", "description": "repo-relative path"},
            "staged": {"type": "boolean"},
        },
        "required": [],
    }

    def run(self, *, base: str | None = None, path: str | None = None, staged: bool = False) -> SkillResult:
        out = self.sb.git_diff(base=base, path=path, staged=staged)
        ev = self.ev.add(kind="git", tool=self.name, args={"base": base, "path": path, "staged": staged}, excerpt=out, path=path)
        return self._result(ev, out or "(no differences)")


class ListFiles(ScoutSkill):
    name = "list_files"
    description = "Inventory of files under a repo-relative directory (path and size), honoring .gitignore and skipping vendor/build/binary/secret files. Bounded."
    schema = {
        "type": "object",
        "properties": {
            "subdir": {"type": "string", "description": "repo-relative directory, '' for root"},
            "max_files": {"type": "integer", "description": "default 500"},
        },
        "required": [],
    }

    def run(self, *, subdir: str = "", max_files: int = 500) -> SkillResult:
        cap = max(1, min(int(max_files), self.sb.limits.max_list))
        files, truncated = self.sb.inventory(subdir, max_files=cap)
        body = "\n".join(f"{f.path}\t{f.size}" for f in files)
        if truncated:
            body += f"\n... [truncated at {cap} files]"
        ev = self.ev.add(kind="inventory", tool=self.name, args={"subdir": subdir, "max_files": cap}, excerpt=body, path=subdir or ".",
                         note=f"{len(files)} files{' (truncated)' if truncated else ''}")
        return self._result(ev, body or "(no files)", count=len(files), truncated=truncated)


class SearchText(ScoutSkill):
    name = "search_text"
    description = "Search text files under the repo for a substring (or a regex with regex=true). Returns path:line: text, bounded."
    schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "subdir": {"type": "string"},
            "regex": {"type": "boolean"},
            "max_hits": {"type": "integer", "description": "default 100"},
        },
        "required": ["pattern"],
    }

    def run(self, *, pattern: str, subdir: str = "", regex: bool = False, max_hits: int = 100) -> SkillResult:
        hits, truncated = self.sb.search(pattern, subdir=subdir, regex=regex, max_hits=max_hits)
        body = "\n".join(f"{p}:{n}: {line}" for p, n, line in hits)
        if truncated:
            body += "\n... [more hits not shown]"
        ev = self.ev.add(kind="search", tool=self.name, args={"pattern": pattern, "subdir": subdir, "regex": regex, "max_hits": max_hits},
                         excerpt=body, path=subdir or ".", note=f"{len(hits)} hits{' (truncated)' if truncated else ''}")
        return self._result(ev, body or "(no matches)", count=len(hits), truncated=truncated)


class ReadFile(ScoutSkill):
    name = "read_file"
    description = "Read a text file (or a 1-based line range of it) from the repo. Bounded to 64 KiB; binaries and secrets are refused."
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path"],
    }

    def run(self, *, path: str, start_line: int = 1, end_line: int | None = None) -> SkillResult:
        text, total, truncated = self.sb.read_text(path, start_line=start_line, end_line=end_line)
        rel = self.sb.rel(self.sb.resolve(path))
        last = total if end_line is None else min(end_line, total)
        numbered = "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(text.splitlines()))
        if truncated:
            numbered += "\n... [file truncated at read limit]"
        ev = self.ev.add(kind="file", tool=self.name, args={"path": rel, "start_line": start_line, "end_line": end_line},
                         excerpt=text, path=rel, lines=[start_line, max(start_line, last)], symbols=extract_symbols(text))
        return self._result(ev, f"{rel} lines {start_line}-{last} of {total}\n{numbered}", total_lines=total, truncated=truncated)


class RunCheck(ScoutSkill):
    name = "run_check"
    description = "Run one of the operator-allowlisted read-only validation commands by name (e.g. a test collection or a linter). No other command exists."
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

    def run(self, *, name: str) -> SkillResult:
        rc, out, truncated = self.sb.run_check(name)
        ev = self.ev.add(kind="check", tool=self.name, args={"name": name, "argv": self.sb.checks[name]}, excerpt=out,
                         note=f"exit {rc}{' (output truncated)' if truncated else ''}")
        return self._result(ev, f"check {name!r} exit {rc}\n{out}", exit_code=rc, truncated=truncated)


SCOUT_SKILLS: dict[str, type[ScoutSkill]] = {
    cls.name: cls for cls in (GitStatus, GitLog, GitDiff, ListFiles, SearchText, ReadFile, RunCheck)
}


def skills_for(sandbox: Sandbox) -> dict[str, type[ScoutSkill]]:
    """run_check is only offered when the operator allowlisted at least one command; git tools
    only when the target is a git repo."""
    out = dict(SCOUT_SKILLS)
    if not sandbox.checks:
        out.pop("run_check")
    if not sandbox.is_git_repo():
        for name in ("git_status", "git_log", "git_diff"):
            out.pop(name)
    return out


__all__ = ["SCOUT_SKILLS", "ScoutSkill", "SandboxError", "skills_for"]
