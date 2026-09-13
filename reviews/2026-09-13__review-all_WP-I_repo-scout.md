# /review-all — WP-I (repo scout + GPU interlock)

- **Date:** 2026-09-13
- **Branch:** `claude/repo-scout` vs `main` (base `6f9bad0`)
- **Diff:** `git diff main...HEAD` — 30 files, +2751/-18; working tree clean
- **Mode:** standard (read-only, report-only). No fix loop.
- **Lenses (blind, parallel):** code-review · security-diff · concurrency/robustness · test-coverage/QA. BIM lens inert (charter forbids BIM/Revit policy here).
- **Prior report:** none → every finding lineage-tags `new`.
- **Profile:** no `.claude/review-profile.yaml`; lens selection by heuristics.

## Recommendation

**Do not merge as-is.** Three findings violate an explicit stated contract of this
work package (scout "never runs a shell / read-only", "secrets never appear in
artifacts"; interlock "two GPU jobs cannot collide"). All three have cheap, local
fixes. Everything else is a follow-up. Advisory only — this is not a merge gate.

---

## BLOCKER

### B1 — Untrusted-repo RCE: `git` runs with target-controlled config (`core.fsmonitor` etc.)
- **Lenses:** security-diff
- **Location:** [scout/sandbox.py:226](scout/sandbox.py:226) (`_git`), reached from every git wrapper and from `run_scout` seeding via `inventory()`/`head_sha()`.
- **Failure path:** `_git` sets only `GIT_TERMINAL_PROMPT=0` and keeps `HOME` in the env. It does not neutralize repo-local `.git/config` or the global config. A target repo shipping `.git/config` with `core.fsmonitor = "<cmd>"` (or `core.pager`, aliases) makes git execute that command during index-refreshing operations — reachable when the model calls `git_status`/`git_diff`, and plausibly during seed `git ls-files`. `shell=False` does not help: git itself spawns the configured command.
- **Consequence:** Arbitrary command execution on the operator's host from a repo the scout was only meant to read. Directly defeats the "never runs a shell / read-only" guarantee. Cloning an OSS repo or investigating a vendored dependency is a realistic scout use, so the target is not fully trusted.
- **Remediation:** In `_git`, prepend hardening overrides that win over on-disk config and clear system/global config:
  ```python
  base = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
          "-c", "protocol.ext.allow=never", "-C", str(self.root)]
  env["GIT_CONFIG_NOSYSTEM"] = "1"; env["GIT_CONFIG_GLOBAL"] = os.devnull
  ```
  Keep `--no-ext-diff` and `GIT_TERMINAL_PROMPT=0`. Add a test: hostile `.git/config` with a `core.fsmonitor` command must not execute.
- **Why retained:** precise location, concrete exploit input, contract-level consequence, cheap feasible fix, code evidence.

### B2 — GPU lock is non-atomic: live holder misread as stale, enabling double-acquisition
- **Lenses:** concurrency/robustness
- **Location:** [aiserver/gpulock.py:156](aiserver/gpulock.py:156)–[164](aiserver/gpulock.py:164) (`acquire` create-then-write), with [:123](aiserver/gpulock.py:123) (`staleness(None)` → "record unreadable" → stale) and [:190](aiserver/gpulock.py:190) (`clear` default `stale_only` removes a stale lock).
- **Failure path:** `acquire` creates the lock file empty via `O_CREAT|O_EXCL`, returns the fd, and only then writes the JSON record. In that window the file exists but is empty. A racing `acquire`/`status` reads it → `json.loads("")` fails → `read_record` returns `None` → `staleness(None)` = stale "record unreadable". An operator (or `clear` with its default `stale_only=True`) then removes the *live* holder's file; the original writer completes onto an orphaned inode and believes it holds the lock, while the path is now free for a second acquirer. Two jobs believe they own the GPU.
- **Consequence:** The mutual-exclusion guarantee the interlock exists for is defeated under a real interleaving (runner swap colliding with a bakeoff); contention messages also misreport live holders as stale.
- **Remediation:** Publish the lock atomically only when complete — write the full record to a temp file in the same dir, then `os.link(tmp, path)` (raises `FileExistsError` if held) and unlink the temp. Alternatively distinguish "empty/partial (writer in progress)" from "corrupt" so a fresh empty file is not immediately declared stale.
- **Why retained:** precise location, concrete interleaving, contract-level consequence, feasible atomic-publish fix, code evidence.

### B3 — Tracked secret files leak through `git_diff` (bypasses the denied-file filter)
- **Lenses:** security-diff
- **Location:** [scout/sandbox.py:266](scout/sandbox.py:266) (`git_diff`; same gap in `git_status`/`git_log`). `read_file`/`search`/`inventory` all consult `is_denied`; the git wrappers do not.
- **Failure path:** A target repo that *tracks* a secret-named file (`.env`, `credentials.json`, `id_rsa`) is diffable. The model calls `git_diff` (e.g. `base="HEAD~50"`, or a working-tree diff of a modified tracked `.env`); git emits the file contents as patch lines, which become the evidence excerpt (≤1200 bytes — enough for a key) written verbatim into `evidence.json` and `transcript.jsonl`. The e2e test only proves an *untracked, gitignored* `.env` stays out; it never diffs a tracked secret.
- **Consequence:** Violates the stated guarantee that `.env*`/denied-prefix contents never reach artifacts. Secret material lands in a durable file under `--out`.
- **Remediation:** Apply the denied-file filter to patch output — pathspec exclusions mirroring `DENIED_FILE_PREFIXES`/`_NAMES` (`-- . ':(exclude).env*' ':(exclude)**/credentials*' …`) or post-filter diff hunks in `git_diff`, dropping any file section whose path satisfies `is_denied`. Same for `git_status` filenames. Add a tracked-secret test.
- **Why retained:** precise location, concrete leak path, contract-level consequence, feasible fix, code evidence. (Trigger is narrower than B1 — requires a committed secret — but it is a direct security-invariant violation, so tiered BLOCKER.)

---

## FOLLOW-UP

### F1 — `_git` / `run_check` timeouts don't kill the process group; a grandchild can hang or orphan
- **Lenses:** concurrency/robustness
- **Location:** [scout/sandbox.py:291](scout/sandbox.py:291) (`run_check`), same pattern in `_git` at [:230](scout/sandbox.py:230).
- **Failure path:** `subprocess.run(..., timeout=…)` with no `start_new_session`. On `TimeoutExpired`, only the direct child is killed; a grandchild inheriting the stdout pipe keeps it open, so the post-timeout `communicate()` blocks until it exits and the grandchild is orphaned. `--check` commands are operator-named but can wrap tools that fork helpers.
- **Consequence:** Documented per-check timeout/output cap silently exceeded; scout hangs; stray process left on the box.
- **Remediation:** `start_new_session=True` and `os.killpg` on timeout before draining (or `Popen`+`communicate(timeout=)` with a group-kill in `finally`). Apply to both.

### F2 — `parse_final_answer` mis-parses when model prose contains braces around the JSON
- **Lenses:** code-review
- **Location:** [scout/evidence.py:131](scout/evidence.py:131) (non-greedy fenced regex) with fallback [:133](scout/evidence.py:133).
- **Failure path:** The fenced-code regex `\{.*?\}` is non-greedy and stops at the first inner `}`, so it never matches the scout's nested report. The `find`/`rfind` fallback rescues the common case (fenced or bare JSON with no other braces) — which is why the e2e test passes. It fails only when surrounding prose also contains braces (e.g. trailing `see {config}`), where `find`→`rfind` spans prose+JSON into invalid text.
- **Consequence:** A correct answer wrapped in brace-bearing prose is classified "not a JSON object" → empty report, exit 4. Local models commonly add a sentence.
- **Remediation:** Make the fenced capture greedy/nesting-tolerant, and/or use `json.JSONDecoder().raw_decode` scanning from the first `{`. Add a nested-JSON-plus-brace-prose test. (Downgraded from the lens's "medium" because the fallback covers the clean case.)

### F3 — `run_under_lock` leaks a raw traceback (and wrong exit code) when `argv[0]` doesn't exist
- **Lenses:** code-review
- **Location:** [aiserver/gpulock.py:208](aiserver/gpulock.py:208) (`Popen(argv)` unguarded); CLI catches only `gpulock.LockError`.
- **Failure path:** `gpu_lock.py run --purpose x -- no-such-cmd` → `Popen` raises `FileNotFoundError` (an `OSError`, not `LockError`) → CLI stack trace instead of a clean `[FAIL]`/exit 3. The lock itself releases correctly via `held`'s `finally`, so no leak.
- **Remediation:** Wrap `Popen` in `try/except OSError as e: raise LockError(...)`, or broaden the CLI `except` to `OSError`.

### F4 — Test gaps on security-boundary and recovery branches (test-coverage lens)
- **Lenses:** test-coverage/QA. Grouped; each is a real branch with no/weak coverage.
  1. **`read_text` NUL-content guard** untested ([scout/sandbox.py](scout/sandbox.py); every "binary" test hits extension-denial, never the content check). Add `blob.dat` = `b"ab\x00cd"` → expect `SandboxError` "binary". *(medium)*
  2. **`search()` large-file skip and in-content NUL skip** untested. Add an oversized file and a NUL-bearing non-denied file. *(medium)*
  3. **`run_under_lock` KeyboardInterrupt path (return 130)** untested — the exact Ctrl-C-during-bakeoff case the interlock handles. *(medium)*
  4. **`run_check` executable-not-found → `SandboxError`** untested (pairs with F3). *(low)*
  5. **`staleness` unparseable-timestamp branch** untested. *(low)*
  6. **`release()` token vs pid guards** not independently exercised — the one test mutates both, so dropping the token check (the per-acquisition security guard) would pass. Add differing-token-only and differing-pid-only cases. *(low)*
  7. **Scout max-turns non-convergence path** untested — a looping model isn't proven bounded, and the non-convergence → exit 4 wiring is unasserted. *(low)*

### F5 — GPU lock stale-detection misses same-host PID reuse
- **Lenses:** concurrency/robustness
- **Location:** [aiserver/gpulock.py:133](aiserver/gpulock.py:133)–[137](aiserver/gpulock.py:137).
- **Failure path:** A crashed holder's PID reused by any unrelated process makes `pid_alive` true, so the lock reads "live" until the 6h age cutoff; default `clear` refuses it. PID reuse is common on long-lived boxes.
- **Consequence:** A crashed exclusive job can block all GPU-exclusive work for up to 6h (or need `clear --force`).
- **Remediation:** Record and compare process start time (`/proc/<pid>/stat` field 22 or `psutil.create_time()`); a PID whose start postdates the lock is dead. Keep the age cutoff as fallback.

### F6 — `clear()` `os.remove` unguarded against concurrent removal
- **Lenses:** concurrency/robustness
- **Location:** [aiserver/gpulock.py:190](aiserver/gpulock.py:190) (contrast `release` at [:173](aiserver/gpulock.py:173) which catches `FileNotFoundError`).
- **Failure path:** Holder releases (or a second `clear`) between the staleness verdict and `os.remove` → uncaught `FileNotFoundError`, traceback, non-zero exit instead of clean "nothing to clear". Two operators clearing the same stale lock reproduce it.
- **Remediation:** Mirror `release`: `try/except FileNotFoundError: return None`, ideally re-verify record identity immediately before removing.

---

## NOT RETAINED

- Generic "add more validation / tests / refactor" — none surfaced; lenses stayed concrete.
- Cross-platform concerns on `gpulock`/`sandbox`: Linux-primary by design (default `/etc/ai-server/bakeoff.lock`), degrades cleanly on Windows, symlink-skip path tested — **intentional, no defect.**
- Cleared by the security lens and not re-raised: `resolve()` rejections (non-str/NUL/absolute/drive/UNC/leading-slash/tilde/`..`/symlink-escape), case-folded `is_denied` on resolved paths, `_REF_RE` closing git-arg injection with `--` before pathspec, `run_check` allowlist (`shell=False`, cwd=root, caps), enforced byte/file/hit/timeout/budget limits, `_scrub_url` dropping URL userinfo.
- `harness/loop.py` + `policy.py` seams: single-threaded, additive, no shared mutable state — no race.
- `bakeoff-session.sh` re-exec: guarded by exported `AISERVER_GPU_LOCKED=1`, runs exactly once, no infinite recursion.

## Provenance summary

| ID | Tier | Lenses | Lineage |
|----|------|--------|---------|
| B1 | BLOCKER | security-diff | new |
| B2 | BLOCKER | concurrency | new |
| B3 | BLOCKER | security-diff | new |
| F1 | FOLLOW-UP | concurrency | new |
| F2 | FOLLOW-UP | code-review | new |
| F3 | FOLLOW-UP | code-review | new |
| F4 | FOLLOW-UP | test-coverage | new |
| F5 | FOLLOW-UP | concurrency | new |
| F6 | FOLLOW-UP | concurrency | new |

No finding was surfaced by more than one lens (the lenses partitioned cleanly);
F3 and F4.4 are the same code area from the bug and coverage angles respectively.
