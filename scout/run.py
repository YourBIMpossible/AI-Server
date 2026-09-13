"""Orchestrate one scout run: validate inputs, seed evidence, drive the harness loop with the
scout's read-only skills, normalise the answer, write the artifacts. The only writes are into
`out_dir` (artifacts + transcript.jsonl) and the aiserver JSONL log."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiserver import LLM, LLMError, get_logger
from aiserver.config import Config
from harness.loop import run as harness_run
from harness.policy import AllowlistReadOnly
from harness.transcript import Transcript

from . import prompts
from .evidence import EvidenceLog, normalize_report, parse_final_answer
from .report import ARTIFACTS, write_artifacts
from .sandbox import Limits, Sandbox, SandboxError, parse_checks
from .tools import skills_for

MAX_SOURCE_BYTES = 200 * 1024
DEFAULT_MAX_TURNS = 24


@dataclass(frozen=True)
class ScoutInputs:
    repo: Path
    task: str
    out_dir: Path
    sources: tuple[Path, ...] = ()
    checks: tuple[str, ...] = ()
    dry_run: bool = False
    max_turns: int = DEFAULT_MAX_TURNS
    limits: Limits = field(default_factory=Limits)


@dataclass(frozen=True)
class ScoutResult:
    out_dir: Path
    artifacts: list[Path]
    parsed: bool          # the model's final answer was a JSON object
    answer: str
    report: dict[str, Any]


def _scrub_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _check_dirs(repo: Path, out_dir: Path) -> None:
    r, o = repo.resolve(), out_dir.resolve()
    if o == r or r in o.parents:
        raise SandboxError(f"output dir must not be inside the target repo: {out_dir}")
    if o in r.parents:
        raise SandboxError(f"output dir must not contain the target repo: {out_dir}")


def _read_sources(paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    out = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            raise SandboxError(f"--source must be an existing file: {p}")
        data = p.read_bytes()
        if len(data) > MAX_SOURCE_BYTES:
            raise SandboxError(f"--source exceeds {MAX_SOURCE_BYTES} bytes: {p}")
        if b"\x00" in data[:8192]:
            raise SandboxError(f"--source must be a text file: {p}")
        out.append({"name": p.name, "path": str(p.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
                    "text": data.decode("utf-8", "replace")})
    return out


def _tool_summary(skills: dict[str, type]) -> str:
    return "\n".join(f"- `{name}`: {cls.description}" for name, cls in sorted(skills.items()))


def run_scout(inputs: ScoutInputs, cfg: Config, llm: LLM | None = None) -> ScoutResult:
    log = get_logger("scout")
    _check_dirs(inputs.repo, inputs.out_dir)
    if not inputs.task.strip():
        raise SandboxError("task description is empty")
    sandbox = Sandbox(inputs.repo, limits=inputs.limits, checks=parse_checks(inputs.checks))
    sha = sandbox.head_sha()
    evidence = EvidenceLog(sha=sha)
    sources = _read_sources(inputs.sources)
    for s in sources:
        evidence.add(kind="input", tool="operator_source", args={"name": s["name"], "sha256": s["sha256"]},
                     excerpt=s["text"], path=s["path"], note="operator-supplied input, not from the target repo")

    # seed: the model always starts from a real top-level inventory and the git position
    files, truncated = sandbox.inventory(max_files=inputs.limits.max_list)
    seed_inv = evidence.add(kind="inventory", tool="list_files", args={"subdir": "", "max_files": inputs.limits.max_list},
                            excerpt="\n".join(f"{f.path}\t{f.size}" for f in files), path=".",
                            note=f"{len(files)} files{' (truncated)' if truncated else ''}")
    seed_ids = [seed_inv.id]
    if sandbox.is_git_repo():
        try:
            seed_ids.append(evidence.add(kind="git", tool="git_log", args={"max_count": 10, "path": None},
                                         excerpt=sandbox.git_log(max_count=10)).id)
        except SandboxError as e:
            log("seed_git_log_failed", error=str(e))

    skills = skills_for(sandbox)
    system_prompt = prompts.render(prompts.load("system"), tool_summary=_tool_summary(skills), max_turns=str(inputs.max_turns))
    seed_text = "; ".join(f"{e.id} ({e.tool}: {e.note or 'see evidence'})" for e in evidence.items if e.id in seed_ids)
    seed_text += f"\n\nTop-level inventory ({seed_inv.note}):\n{seed_inv.excerpt}"
    src_text = "\n\n".join(f"### {s['name']} (sha256 {s['sha256'][:12]})\n```\n{s['text']}\n```" for s in sources) or "(none)"
    checks_text = "\n".join(f"- `{n}` -> `{' '.join(a)}`" for n, a in sorted(sandbox.checks.items())) or "(none)"
    task_msg = prompts.render(prompts.load("task"), task=inputs.task, git_sha=sha or "not a git repository",
                              seed_evidence=seed_text, sources=src_text, checks=checks_text)

    started = datetime.now(timezone.utc).replace(microsecond=0)
    transcript_path = inputs.out_dir / "transcript.jsonl"
    answer = ""
    if inputs.dry_run:
        log("dry_run", out_dir=str(inputs.out_dir))
    else:
        llm = llm or LLM(cfg)
        transcript = Transcript(transcript_path)
        try:
            answer = harness_run(
                task_msg, llm, AllowlistReadOnly(skills), out_dir=inputs.out_dir, run_id="scout",
                skills=skills, system_prompt=system_prompt, max_turns=inputs.max_turns,
                make_skill=lambda cls, llm_: cls(llm_, sandbox=sandbox, evidence=evidence),
                transcript=transcript,
            )
        except LLMError as e:
            log("model_error", error=str(e))
            answer = ""
            _write(inputs, cfg, sha, started, evidence, sources, answer, stop=f"model error: {e}", transcript_path=transcript_path)
            raise
    parsed_obj = parse_final_answer(answer) if answer else None
    stop = None if parsed_obj is not None else ("dry run: model not called" if inputs.dry_run else "final answer was not a JSON object; see transcript")
    artifacts, report = _write(inputs, cfg, sha, started, evidence, sources, answer, stop=stop, parsed=parsed_obj, transcript_path=transcript_path)
    log("finished", out_dir=str(inputs.out_dir), facts=len(report["facts"]), inferences=len(report["inferences"]),
        unknowns=len(report["unknowns"]), parsed=parsed_obj is not None, tool_calls=len(evidence.tool_calls))
    return ScoutResult(inputs.out_dir, artifacts, parsed_obj is not None, answer, report)


def _write(inputs, cfg, sha, started, evidence, sources, answer, *, stop, parsed=None, transcript_path):
    report = normalize_report(parsed, evidence.ids())
    if stop and not report["stop_reason"]:
        report["stop_reason"] = stop
    meta = {
        "task": inputs.task,
        "target": str(inputs.repo.resolve()),
        "git_sha": sha,
        "model": cfg.model,
        "runtime": _scrub_url(cfg.inference_base_url),
        "prompt_version": prompts.PROMPT_VERSION,
        "timestamp": started.isoformat(),
        "dry_run": inputs.dry_run,
        "max_turns": inputs.max_turns,
        "sources": [{"name": s["name"], "sha256": s["sha256"]} for s in sources],
        "checks_allowlisted": sorted(parse_checks(inputs.checks)),
        "checks_run": [f"{e.args['name']}: {e.note}" for e in evidence.items if e.kind == "check"],
        "tool_calls": evidence.tool_calls,
        "transcript": transcript_path.name if transcript_path.exists() else None,
        "answer_parsed": parsed is not None,
    }
    artifacts = write_artifacts(inputs.out_dir, meta, evidence.to_obj(), report)
    if answer and parsed is None:
        (inputs.out_dir / "raw-answer.txt").write_text(answer, encoding="utf-8")
    return artifacts, report


__all__ = ["ARTIFACTS", "ScoutInputs", "ScoutResult", "run_scout"]
