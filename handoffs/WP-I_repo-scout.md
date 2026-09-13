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
| Prompt text | `aiserver/prompts.py` holds inline templates today; the scout template is a **versioned file** `scout/prompts/scout-v1.md` (mandate) rendered by the same `{placeholder}` convention |

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
  `run.py` (orchestration), `cli.py`, `__main__.py`, `prompts/scout-v1.md`.
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

- [x] **P0** — survey conventions, this plan, commit.
- [ ] **P1** — policy docs: benchmark policy, production contract, env-gap follow-up.
- [ ] **P2** — GPU interlock: `aiserver/gpulock.py`, config key, `scripts/gpu_lock.py`,
      session wrapper, tests.
- [ ] **P3** — scout sandbox + tools + harness seams, tests.
- [ ] **P4** — prompt template, evidence schema, artifact rendering, CLI, e2e fixture test.
- [ ] **P5** — eval-case proposals, README, full suite, final handoff (below).

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

## Final handoff

Filled in at P5: files changed, commands run + results, example invocation, deferred work,
operator decisions.
