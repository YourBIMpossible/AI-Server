#!/usr/bin/env python3
"""One real automation, graded: run daily-digest against an endpoint and score what it wrote.

    python scripts/automation_acceptance.py --label ollama [--base-url URL] [--model M]

Meant to be started by a scheduler (systemd timer), not by hand -- the acceptance question is
whether the job works unattended, start to finish.

1. Workspace: the real job reads BIMpossible_Workspace/01_BuildLog and AI-Brain-Data/decision-log,
   which live on the rig, not on the box. So the box gets a workspace built from its OWN
   engineering record, under out/box-workspace/:
   - one build-log file per day, from real git history (this repo, plus local-intel when present)
   - the box's Phase 0 remeasure decision doc
   It is a generated copy under out/. Nothing is written to the real AI-Brain-Data or
   BIMpossible_Workspace, and nothing here is client data.
2. Runs `python -m automation daily-digest` unchanged, with WORKSPACE/OUT pointed at it.
3. Grades the digest with the WP-F scorer and judge (eval/automation_rubrics/daily-digest-box.json),
   including judge calibration.
Writes out/acceptance/<label>-<UTC>.json. Exit 0 only when the job succeeded and the grade passed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from aiserver import LLM, LLMError, load_config  # noqa: E402
from eval.judge import judge  # noqa: E402
from eval.run import calibrate_judge  # noqa: E402
from eval.scoring import passed, score  # noqa: E402

RUBRIC_FILE = REPO / "eval" / "automation_rubrics" / "daily-digest-box.json"
DECISION_REF = "box-phase0:decisions/2026-09-13__box-phase0-remeasure.md"


def git_days(repo: Path, ref: str, days: int) -> dict[str, list[str]]:
    """{YYYY-MM-DD: ["subject", ...]} for commits on `ref` in the last `days` days."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", ref, f"--since={days} days ago", "--date=short", "--format=%ad%x09%s"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    by_day: dict[str, list[str]] = {}
    for line in out.splitlines():
        day, _, subject = line.partition("\t")
        if not subject.startswith("Merge pull request"):
            by_day.setdefault(day, []).append(subject)
    return by_day


def build_workspace(root: Path, repos: list[tuple[str, Path, str]], decision_text: str | None, days: int = 7) -> Path:
    build_log = root / "BIMpossible_Workspace" / "01_BuildLog"
    decision_log = root / "AI-Brain-Data" / "decision-log"
    build_log.mkdir(parents=True, exist_ok=True)
    decision_log.mkdir(parents=True, exist_ok=True)
    merged: dict[str, list[str]] = {}
    for label, path, ref in repos:
        for day, subjects in git_days(path, ref, days).items():
            merged.setdefault(day, []).extend(f"[{label}] {s}" for s in subjects)
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    for day in sorted(merged):
        if day < cutoff:
            continue
        body = f"# Build log — {day}\n\n" + "\n".join(f"- {s}" for s in merged[day]) + "\n"
        (build_log / f"{day}.md").write_text(body, encoding="utf-8")
    if decision_text:
        (decision_log / "2026-09-13__box-phase0-remeasure.md").write_text(decision_text, encoding="utf-8")
    now = time.time()
    for p in list(build_log.glob("*.md")) + list(decision_log.glob("*.md")):
        os.utime(p, (now, now))  # inside the job's DIGEST_DAYS window
    return root


def grade(digest: str, rubric: dict, *, judge_llm, judge_model: str | None, threshold: float) -> dict:
    kw = score(digest, rubric)
    verdict, raw = None, None
    if rubric.get("judge"):
        try:
            verdict, raw = judge(judge_llm, rubric["judge"], digest, model=judge_model)
        except LLMError as e:
            verdict, raw = False, f"judge error: {e}"
    final = kw if verdict in (None, True) else 0.0
    return {"keyword_score": kw, "judged": verdict, "judge_raw": raw, "score": final, "passed": passed(final, threshold)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", required=True, help="runner label for the result file")
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--out", type=Path, default=REPO / "out")
    args = ap.parse_args(argv)

    overrides = {k: v for k, v in {"INFERENCE_BASE_URL": args.base_url, "INFERENCE_MODEL": args.model}.items() if v}
    cfg = load_config(overrides=overrides)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ws = args.out / "box-workspace"
    run_out = args.out / "acceptance" / f"{args.label}-{stamp}"

    try:
        decision = subprocess.run(["git", "-C", str(REPO), "show", DECISION_REF],
                                  capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        decision = None
    repos = [("AI-Server", REPO, "HEAD")]
    li = Path(os.environ.get("LOCAL_INTEL_REPO", Path.home() / "local-intel"))
    if li.exists():
        repos.append(("local-intel", li, os.environ.get("LOCAL_INTEL_REF", "HEAD")))
    build_workspace(ws, repos, decision)

    env = {**os.environ, "WORKSPACE": str(ws), "OUT": str(run_out), "DIGEST_DAYS": "7",
           "INFERENCE_BASE_URL": cfg.inference_base_url, "INFERENCE_MODEL": cfg.model}
    t0 = time.perf_counter()
    job = subprocess.run([sys.executable, "-m", "automation", "daily-digest"], cwd=REPO, env=env,
                         capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    digests = sorted(run_out.glob("digest-*.md"))
    digest = digests[-1].read_text(encoding="utf-8") if digests else ""

    rubric = json.loads(RUBRIC_FILE.read_text(encoding="utf-8"))["rubric"]
    judge_model = cfg.eval_judge_model or cfg.model
    judge_llm = LLM(cfg, timeout=900)
    result = {
        "label": args.label, "utc": stamp, "endpoint": cfg.base_url, "model": cfg.model, "judge_model": judge_model,
        "job_exit": job.returncode, "job_stdout": job.stdout[-2000:], "job_stderr": job.stderr[-2000:],
        "job_seconds": round(elapsed, 1), "digest_file": str(digests[-1]) if digests else None,
        "workspace": str(ws), "invoked_by": os.environ.get("INVOCATION_ID") and "systemd" or "shell",
    }
    if job.returncode == 0 and digest:
        result["grade"] = grade(digest, rubric, judge_llm=judge_llm, judge_model=judge_model,
                                threshold=cfg.eval_pass_threshold)
        result["judge_calibration"] = calibrate_judge(judge_llm, judge_model)
    else:
        result["grade"] = {"passed": False, "why": "job failed or wrote no digest"}
    ok = job.returncode == 0 and result["grade"]["passed"]
    result["accepted"] = ok
    dest = args.out / "acceptance" / f"{args.label}-{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[{'OK' if ok else 'FAIL'}] {args.label}: job exit {job.returncode}, grade {result['grade']}. Wrote {dest}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
