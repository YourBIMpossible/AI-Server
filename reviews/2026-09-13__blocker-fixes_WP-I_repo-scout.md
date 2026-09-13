# WP-I merge-blocker fixes — repo-scout

Companion to `2026-09-13__review-all_WP-I_repo-scout.md` (the source-of-truth decision list).
Fixes the three verified BLOCKERs plus the two adjacent follow-ups (F3, F6) needed for a correct
B2 lifecycle. Branch `claude/repo-scout`. Not committed (per the fix mandate's no-commit constraint).

## 1. Files changed

| File | Change |
|------|--------|
| `scout/sandbox.py` | B1 git hardening (`_GIT_HARDENING`, `_git` env isolation); B3 `git_diff` denied-path filter + `_allowed_diff_paths` |
| `aiserver/gpulock.py` | B2 atomic publication in `acquire`; non-auto-stale unreadable records in `staleness`; F6 guarded `clear`; F3 argv validation in `run_under_lock` |
| `tests/test_gpulock.py` | Updated to safe B2 semantics; added publication/contention/vanish/F3 tests |
| `tests/test_scout_sandbox.py` | Added B1 hostile-config test and B3 diff-leakage/rename tests |

## 2. Root cause and fix

**B1 — Git config command-execution.** A target repo's own `.git/config` is always read by git and
cannot be disabled by environment variables; command-valued keys (`core.fsmonitor`, `core.pager`,
`diff.external`/textconv, hooks, `core.sshCommand`, `credential.helper`, `ext::`) would run arbitrary
programs during ordinary inspection. *Fix:* every scout git call now goes through `_git`, which (a)
prepends command-line `-c` overrides (`_GIT_HARDENING`) that win over every config file and neutralise
each command-valued key, and (b) runs with a scrubbed env that reads no global/system config
(`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM=os.devnull`), never prompts
(`GIT_TERMINAL_PROMPT=0`), and pins a deterministic `core.autocrlf=input` so config isolation does not
change diff output across hosts. `shell=False` throughout.

**B2 — GPU-lock publication race.** `acquire` created the lock file empty (`O_CREAT|O_EXCL`) then wrote
the record in a second step; a concurrent reader could observe an empty/partial lock, and unreadable
content was treated as automatically stale (`staleness(None) -> True`), so recovery could delete a lock
a holder was mid-writing. *Fix:* `acquire` now serialises the complete record into a sibling temp file
(write+flush+fsync) and publishes it with an atomic `os.link`; `FileExistsError` means the lock is held.
The temp file is always unlinked. `staleness(None)` returns `(False, …)` — empty/partial/malformed/
temporarily-unreadable content is never auto-stale and is never auto-removed; genuine staleness still
requires a *parseable* record showing a dead local pid or an over-age start. Stale recovery stays
operator-only (`clear`/`clear --force`); nothing kills a process.

**B3 — Denied-path leak via `git diff`.** `git_diff` could emit the contents of denied files
(`.env`, keys, credentials) into tool output, evidence, transcript and reports. *Fix:* `git_diff` first
enumerates changed paths with `git diff --name-status -z` (no content), drops every denied path via the
same `is_denied` policy used by reads (a rename/copy is kept only if *both* endpoints are allowed), then
emits the patch restricted to the surviving paths using `:(literal)` pathspecs. `--no-ext-diff` and
`--no-textconv` are always set; a direct request for a denied `path` raises; no allowed files → `""`.

## 3. Safety invariants now enforced

- A hostile target-repo (or global/system) git config cannot make any scout git operation execute an
  external command — proven across `rev-parse`, `status`, `log`, `diff`, path-scoped `diff`.
- Two contenders cannot both hold a live GPU lock; a published lock is always a complete, parseable
  record (no empty/partial window); an unreadable lock is never auto-deleted.
- No denied-file content can appear in diff output, captured output, evidence, transcript, or reports —
  including via renames into a denied name and filenames with spaces.

## 4. Tests added + results

Added to `tests/test_gpulock.py`: `test_clear_removes_genuinely_stale_lock`,
`test_clear_preserves_unreadable_lock_unless_forced`,
`test_acquire_publishes_atomically_without_partial_or_leftover`,
`test_two_contenders_cannot_both_acquire`, `test_clear_tolerates_lock_vanishing_mid_remove`,
`test_run_under_lock_rejects_unlaunchable_command_and_releases`; updated `staleness(None)` assertion,
malformed-lock clear behaviour, and the CLI garbage-lock case.

Added to `tests/test_scout_sandbox.py`: `test_hostile_repo_config_cannot_run_external_command`
(positive control proves the vector is live, then proves the sandbox fires none),
`test_git_diff_never_leaks_denied_file_contents`, `test_git_diff_rename_into_denied_name_is_excluded`.

`python -m pytest -q` → **288 passed, 1 skipped** (skip = pre-existing "symlinks unavailable on this
host"). No existing test weakened. CI defines no linter/type-check step (`pytest -q` only);
`py_compile` clean on all edited modules.

## 5. F3 / F6

- **F6 fixed** — required for a correct B2 lifecycle: `clear`'s `os.remove` is now guarded with
  `except FileNotFoundError: return None`, mirroring `release`, so concurrent recovery doesn't traceback.
- **F3 fixed** — small argv validation in `run_under_lock`: empty argv and unlaunchable `argv[0]`
  (`OSError`) now surface as `LockError`, handled by the CLI's single error path (exit 3) instead of a
  raw traceback; the lock is still released.

## 6. Unresolved follow-ups (NOT addressed here)

- **F1** subprocess process-group / signal propagation on `run_under_lock` children.
- **F2** `parse_final_answer` brittleness (downgraded to low in the review; find/rfind fallback rescues
  the clean case).
- **F4** remaining test-coverage gaps beyond those added here.
- **F5** PID-reuse can mask a stale lock (a dead pid's number reused by a live process reads as live).

These remain open; nothing above resolves them.

## 7. Merge readiness

The three BLOCKERs are fixed with proving regression tests and the full suite is green with no existing
test weakened. From the blocker set this branch is merge-ready; F1/F2/F4/F5 remain as tracked
follow-ups, none of them a merge gate per the review's tiering.
