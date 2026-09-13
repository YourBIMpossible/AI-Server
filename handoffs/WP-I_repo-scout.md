# WP-I — Repo scout: read-only evidence compiler + GPU-work interlock + operating policy

**Goal:** the first everyday local-AI workflow — repo/task in, evidence-backed project map,
risk-aware implementation plan, verification plan and a compact handoff out — run by the
production model through a strictly read-only tool set. Plus the two operating documents the
box has been running without (benchmark policy, production model/runtime contract) and the
exclusive-GPU-work interlock WP-H left as a stub.
**Depends on:** WP-A core library, `harness/` (tool loop), WP-F/WP-H **complete on main, not
rerun here** (`decisions/2026-09-13__wp-f-eval-separates-models.md`,
`decisions/2026-09-13__wp-h-runner-bakeoff.md`).
**Status:** in progress on `claude/repo-scout` (branched from `main` @ 6f9bad0, 2026-09-13).

---

## What this is, and is not

A **local engineering analyst and evidence compiler**. It inspects one target repo through
narrow server-side tools, cites what it found (path, symbol, line range, Git SHA, excerpt),
separates facts from inferences, says "unknown" when evidence is missing, and writes five
artifacts into an output directory. It never modifies the target, never runs arbitrary
commands, never reaches outside the target repo + explicit inputs + output dir, and never
touches secrets, cloud credentials, mail, browser data, production services or client data.

It is **not** an autonomous coding agent. There is no write-capable skill, no shell tool, no
commit/push/PR/deploy path. Provider-agnostic: only `aiserver.client.LLM` talks to a model.

## Repository-grounded plan (Phase 0 output)

Existing files and conventions reused — nothing below is invented:

| Need | Reuse |
|---|---|
| Model access | `aiserver.client.LLM.chat_message(messages, tools=...)` (OpenAI tool-call surface; `PromptTooLargeError` guard) |
| Tool loop | `harness.loop.run()` + `harness.registry.Skill/register/validate_args` + `harness.policy.RunPolicy` + `harness.transcript.Transcript` |
| Config | `aiserver.config.load_config()` / `_DEFAULTS` (new key `GPU_LOCK_PATH`) |
| Logging | `aiserver.log.get_logger()` JSONL |
| CLI shape | argparse `main(argv) -> int` as in `scripts/*.py`, `eval/bakeoff/run.py`; `python -m <pkg>` via `<pkg>/__main__.py`; `[project.scripts]` entry |
| Tests | `tests/conftest.py` `_sequenced_server` / `_running` stdlib mock endpoint; tool-call body shape from `tests/test_harness_loop.py` |
| Docs | `decisions/YYYY-MM-DD__slug.md`, `handoffs/WP-<L>_<slug>.md`, ops config under `ops/` |
| Prompt text | `aiserver/prompts.py` holds inline templates today; the scout templates are **versioned files** `scout/prompts/v1/{system,task}.md` rendered with `{{placeholder}}` (double braces — the templates contain JSON) |

Files this work package adds or changes:

- `aiserver/gpulock.py` — exclusive-GPU-work interlock (decision 2). Honors the WP-H
  convention (`/etc/ai-server/bakeoff.lock`, read by Personal-OCR's `WP_H_BAKEOFF_LOCK`);
  `GPU_LOCK_PATH` config key overrides. Atomic `O_EXCL` create, JSON record, stale detection
  without killing anything, operator-only `clear`.
- `aiserver/config.py` — `GPU_LOCK_PATH` default + `Config.gpu_lock_path`.
- `scripts/gpu_lock.py` — `status | run --purpose P -- cmd… | clear [--stale-only]`.
- `scripts/bakeoff-session.sh` — one-line re-exec under the lock (`AISERVER_NOLOCK=1` to skip);
  WP-H measurement logic untouched.
- `harness/loop.py` — `run(..., skills=None, system_prompt=None, max_turns=None)` (additive;
  defaults unchanged) so the scout can expose only its own skills.
- `harness/policy.py` — `AllowlistReadOnly(names)` policy.
- `scout/` package: `sandbox.py` (path validation, limits), `tools.py` (skills:
  `git_status`, `git_log`, `git_diff`, `list_files`, `search_text`, `read_file`, `run_check`),
  `evidence.py` (schema + validator + deterministic ordering), `report.py` (five artifacts),
  `run.py` (orchestration), `cli.py`, `__main__.py`, `prompts/v1/{system,task}.md`.
- `pyproject.toml` — `scout` package + package data + `run-scout` script.
- `tests/test_gpulock.py`, `tests/test_scout_sandbox.py`, `tests/test_scout_tools.py`,
  `tests/test_scout_evidence.py`, `tests/test_scout_e2e.py`.
- `decisions/2026-09-13__benchmark-policy.md` (decision 1).
- `ops/PRODUCTION-CONTRACT.md` (decision 3).
- `decisions/2026-09-13__scheduled-acceptance-env-gap.md` (decision 9).
- `decisions/2026-09-13__scout-eval-case-proposals.md` (decision 8 — proposals, not live cases:
  adding cases is itself a full-eval trigger under the benchmark policy).
- `README.md` — one section for the scout and the lock.

## Phases (LONG-TASK-HARNESS)

- [x] **P0** — survey conventions, this plan, commit. (57e68e7)
- [x] **P1** — policy docs: benchmark policy, production contract, env-gap follow-up. (6d0398d)
- [x] **P2** — GPU interlock: `aiserver/gpulock.py`, config key, `scripts/gpu_lock.py`,
      session wrapper, tests. (92e0f75)
- [x] **P3** — scout sandbox + tools + harness seams, tests. (b267a12)
- [x] **P4** — prompt template, evidence schema, artifact rendering, CLI, e2e fixture test. (3bbf521)
- [x] **P5** — eval-case proposals, README, full suite, final handoff (below).

## Safety rules enforced in code

- Every tool path argument is repo-relative, normalized, resolved; `..`, absolute paths,
  and symlinks resolving outside the target root are rejected.
- Output dir must not lie inside the target repo; the scout writes nowhere else.
- No skill takes a shell string. `run_check` runs only operator-named entries
  (`--check NAME=argv…`), `shell=False`, cwd = target, scrubbed env, timeout, output cap.
- Bounded: file-count, bytes-per-read, search hits, per-result bytes, per-run wall clock.
- Skipped by inventory: `.git`, `.env*`, `node_modules`, venvs, `out/`, build/dist/vendor,
  binaries. `.gitignore` honored via `git ls-files --exclude-standard` when the target is a
  repo.
- Model output facts must cite evidence ids the run actually produced; uncited claims are
  demoted to inferences, never promoted to facts.

## Acceptance

- `python -m pytest` green on Windows dev rig and CI (no GPU, no live endpoint).
- E2E fixture test: report names real fixture files/symbols, carries the fixture Git SHA,
  separates facts from inferences, reports a known unknown, writes nothing into the fixture.
- Interlock tests: acquire/release, contention, stale detection, no process is ever killed.
- WP-F/WP-H artifacts untouched; production model settings untouched; nothing run on the GPU.

## Final handoff (2026-09-13, branch `claude/repo-scout`, base `main` @ 6f9bad0)

### Files changed

| Area | Files |
|---|---|
| GPU interlock | `aiserver/gpulock.py` (new), `aiserver/config.py` (`GPU_LOCK_PATH` / `Config.gpu_lock_path`), `.env.example`, `scripts/gpu_lock.py` (new), `scripts/bakeoff-session.sh` (re-exec under lock; `AISERVER_NOLOCK=1` skips) |
| Harness seams | `harness/loop.py` (`run(..., skills, system_prompt, max_turns, make_skill, transcript)`, defaults unchanged), `harness/policy.py` (`AllowlistReadOnly`) |
| Scout | `scout/__init__.py`, `sandbox.py`, `tools.py`, `evidence.py`, `report.py`, `run.py`, `cli.py`, `__main__.py`, `prompts/__init__.py`, `prompts/v1/system.md`, `prompts/v1/task.md` |
| Packaging | `pyproject.toml` (`scout`, `scout.prompts` packages, prompt package-data, `run-scout` script) |
| Tests | `tests/test_gpulock.py` (11), `tests/test_scout_sandbox.py` (10), `tests/test_scout_tools.py` (9), `tests/test_scout_evidence.py` (7), `tests/test_scout_e2e.py` (5) |
| Docs | `decisions/2026-09-13__benchmark-policy.md`, `ops/PRODUCTION-CONTRACT.md`, `decisions/2026-09-13__scheduled-acceptance-env-gap.md`, `decisions/2026-09-13__scout-eval-case-proposals.md`, `README.md` (two sections), this anchor |

Not touched: `eval/cases.jsonl`, `eval/bakeoff/*`, WP-F/WP-H results, production `.env`,
runner configs. Nothing was run on the GPU or against a live endpoint.

### Commands run and results

- `python -m pytest -q` (Windows rig, py3.12) → **280 passed, 1 skipped, 80s**. The skip is
  `test_symlink_escape_is_rejected` when the host cannot create symlinks; on Linux CI it runs.
- Targeted: `tests/test_gpulock.py tests/test_config.py` → 31 passed; `tests/test_harness_*`
  → 11 passed (harness defaults unchanged); `tests/test_scout_*` → 30 passed, 1 skipped.
- `python -m scout --repo . --task "Where does the aiserver package enforce the input-token limit, and which tests cover it?" --dry-run --out $TEMP/scout-demo`
  → exit 0, five artifacts, seed evidence E1 (top-level inventory) + E2 (git log), git SHA
  recorded, no model call.

### Example invocation (on the box, `~/AI-Server` venv, `.env` pointing at the endpoint)

```bash
python -m scout --repo ~/some-repo --task "Add a --json flag to the export command" \
  --source ~/notes/acceptance.md \
  --check tests="python -m pytest --collect-only -q" \
  --out out/scout/demo
```

Exit codes: 0 ok · 1 endpoint/model error · 2 usage/sandbox error · 4 the answer was not a
JSON object (artifacts still written; `raw-answer.txt` + `transcript.jsonl` alongside).
Ordinary scout runs do **not** take the GPU lock; they are inference, not GPU-exclusive work.

### Safety properties, where enforced

- Path scope: `scout/sandbox.py::Sandbox.resolve` (absolute, drive-letter, UNC, `~`, `..`,
  NUL, symlink-escape all rejected); tests in `test_scout_sandbox.py`.
- No writes to target: no skill has a write path; `test_tools_never_write_into_target`,
  `test_end_to_end_fixture_repo` (byte snapshot before/after).
- Out-dir rules: `scout/run.py::_check_dirs` (not inside the repo, not containing it).
- No arbitrary exec: `run_check` only runs `--check NAME=argv` entries, `shell=False`, scrubbed
  env, timeout, output cap; git runs with fixed argv + `GIT_TERMINAL_PROMPT=0`.
- Secrets: `.env*`, key files, `credentials*`, binaries never listed/read/searched.
- Citation honesty: `scout/evidence.py::normalize_report` demotes facts whose citations are not
  ids from this run; never promotes. E2E proves a fabricated `E42` claim lands under
  *Inferences*.
- Knowledge/RAG skill is not reachable: `SCOUT_SKILLS` is a separate map, not the harness
  `REGISTRY`; `AllowlistReadOnly` refuses anything else.

### Intentionally deferred

- **Live smoke test against the box.** No opt-in integration tier exists in `tests/` and the
  mandate said not to invent one; run the example invocation by hand as the first live check.
- **Bakeoff scripts resolving `python3` from the system.** Documented in
  `decisions/2026-09-13__scheduled-acceptance-env-gap.md`; fix is a one-line `PYTHON=` default
  to the venv interpreter, out of scope for a "no WP-H changes" batch.
- **Eval cases for the scout.** Five proposed in
  `decisions/2026-09-13__scout-eval-case-proposals.md`; adding them triggers a full eval under
  the benchmark policy, so they are not in `cases.jsonl`.
- **Prompt tuning for gemma4.** v1 prompts are written from the mandate, not from observed
  gemma4 output. Expect a `v2` after the first few live runs; bump by adding a directory, never
  by editing `v1`.

### Operator decisions remaining

1. On the box, create the lock directory once: `sudo install -d -m 0775 -o "$USER" -g "$USER" /etc/ai-server`
   (see `ops/PRODUCTION-CONTRACT.md`). Until then `bakeoff-session.sh` fails fast with a
   pointer to that step; set `AISERVER_NOLOCK=1` to bypass deliberately.
2. Whether to adopt the five proposed eval cases (one full-eval cycle).
3. First live scout run on the box and a read of the artifacts — that is the real acceptance
   for the prompt, and the input for `v2`.
4. Merge: this branch is ready for a PR to `main`; nothing has been pushed.
