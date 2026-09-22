# BIMpossible PR #671: resolution plan

**Status:** proposed, 2026-09-21. It is waiting on the owner's pick of path (a), (b) or (c).
**PR:** `fix/wfa0914-firm-scoped-ai-policy`, which covers the firm-scoped AI-context policy,
the fail-closed lookup and the live handle re-check (WFA 2026-09-14 L3:
SEC-1/CHAIN-2/CQ-1/SLOP-1/SEC-6).
**Evidence:** `decisions/2026-09-21__personal-ai-and-pr671-ci-plan.md` Part 1. The source plan
is kept for reference in `handoffs/LOCAL-AI-CI-PLAN-PR671-2026-09-21.md`.
**Repo:** all of the work happens in `F:\BIMpossible`. This file lives in AI-Server only
because that is where the decision was made.

## Where #671 stands (measured on head `395d138f`, 2026-09-21)

| Item | State |
|---|---|
| Merge state | CONFLICTING/DIRTY against `main` |
| Conflicts | `cross_firm_sharing.py`, `hub_tenancy.py`, `router.py`. These are tenant-isolation surfaces |
| Migration id | `e5f6a7b8c9d1` collides with PR #677. The rename to `a4c1e9b73f52` is in local commit `07731a4d`, **unpushed** |
| NL-filter offline lane | PASS. Score 1.0, exit 0, `drift=nl_filter_source_sha256` |
| `prompt_sha256` | unchanged. The model-facing prompt did not move |
| `tests/eval/test_nl_filter_monitor.py` | **3 failed / 36 passed**. The cause is the whole-file source-hash pin |
| Remote checks | gitleaks only, passing |

**Three blockers, and they are independent of each other:**
1. The NL-filter pytest drift.
2. The tenant-isolation conflicts.
3. The unpushed migration rename.

## Decision: the local-AI CI plan is not the unblock

A local-model runner measures a different model from the pinned `claude-haiku-4-5`, which is
the one production calls. Once the source hash stops counting as drift, #671 needs **no**
behavioural evidence from any provider. The local runner stays on the AI-Server roadmap as its
own cross-repo item.

## Owner call: how to clear blocker 1

| Path | What | Cost | Verdict |
|---|---|---|---|
| **(a)** | A pin-split PR to `main` first (Phase A below), then rebase #671 onto it | $0, about 1 day | **Recommended** |
| (b) | A paid live run on #671 (`--mode live --repeats 10`, about 160 Haiku calls, about 3 min), then `--write-baseline` | Paid | Clean, but pays to prove that an unchanged prompt is unchanged |
| (c) | `--write-baseline` alone on #671; the live evidence gets marked `stale` | $0 | Quick hack. `CLAUDE.md:53` forbids "`--update-baseline` to unblock". Rejected |

The phases below assume (a). Under (b), Phase A is replaced by one live run plus a re-pin
commit on the #671 branch, and phases B–E stay the same.

---

## Phase A: pin-split PR (BIMpossible, new branch off `main`)

**Scope.** Only these files:
- `backend/tests/eval/nl_filter_monitor.py`
- `backend/tests/eval/nl_filter_baseline.json`
- `backend/tests/eval/test_nl_filter_monitor.py`
- `docs/CI-GATES.md`

It does not touch `nl_filter.py` or #671's branch.

Work red-green (`/tdd`): write the failing tests first.

1. **Make the source hash provenance-only.** Move `nl_filter_source_sha256` out of the
   behavioural pins into a `provenance` block. It is still recorded and still printed, and it
   is excluded from `_drift()` and from `live_rerun_required`.
2. **Fill the hole this opens.** The whole-file hash currently also covers model-facing things
   that sit outside the prompt template literal. Add `model_config_sha256`, a hash over the
   call parameters:
   - model resolution;
   - temperature and other sampling settings;
   - max tokens;
   - response-format or schema settings;
   - the grounding cap `MAX_VALUES_PER_COLUMN`, if it isn't already pinned.

   Extract these by AST or by a named constant, the same way `prompt_sha256` is extracted. If
   a parameter can't be isolated cleanly, keep it under a narrower hash rather than dropping
   it.
3. **Stop the two exact-dict tests depending on ambient drift.**
   `test_pin_drift_is_reported_but_does_not_fail` and
   `test_a_pin_missing_from_the_baseline_is_reported_as_drift` should assert on the key they
   changed, not on the whole `drift` dict.
4. **Add tests.** Each new test must fail first, before the change that makes it pass.
   - **Source-only edit.** A comment or pre-model edit to `nl_filter.py` changes only the
     provenance hash, and the result is `drift == {}`.
   - **Config edit.** Changing a sampling or token parameter reports
     `model_config_sha256: changed`.
   - **Migration.** An old baseline that has `nl_filter_source_sha256` under `pins` loads
     cleanly, and the migration keeps the recorded live evidence linked, never silently
     cleared.
   - **Write-baseline.** `write_baseline_pins()` still never touches `thresholds`.
5. **Re-pin `main`.** Use `--write-baseline` on `main`. This is legitimate here, because no
   behavioural pin moves on `main`: only the pin *structure* changes. Say that in the commit
   message.
6. **Update the docs.** In `docs/CI-GATES.md`, add the provenance-versus-behavioural rule to
   § "Drift is reported, never failed".
7. **Validate.** Run `Verify-Local-CI.ps1` with no key set. Push through
   `Push-And-Verify.ps1`, then open the PR.

**Stays exactly as it is:**
- the thresholds;
- the live half;
- the 14-day staleness report;
- stale-marking on re-pin;
- exit codes 0, 1 and 2.

**Exit:** the pin-split PR is merged to `main`, and its pytest run is green with no API key.

## Phase B: rebase #671 (security-sensitive, done by hand)

1. Use a fresh worktree:

   ```bash
   git worktree add .claude\worktrees\pr671 fix/wfa0914-firm-scoped-ai-policy
   ```

   Carry `07731a4d` across if it lives in another tree.
2. Rebase onto `main`, which now includes Phase A.
3. Resolve `cross_firm_sharing.py`, `hub_tenancy.py` and `router.py` **by hand**. For each
   hunk, keep both main's tenant rule and #671's firm-scoped rule. Where they conflict, the
   stricter one wins, and the decision is noted in the commit.
4. Keep `07731a4d` as the migration id `a4c1e9b73f52`. Confirm that `alembic heads` shows one
   head, and that #677's id is untouched.

**Exit:** a clean rebase and a single Alembic head.

## Phase C: security review of the resolved conflicts

1. Run a `security-engineer` review of the conflict hunks only (`git range-diff` before and
   after), focused on cross-firm leakage, fail-open paths and inherited opt-ins.
2. Run the auto-gate agents from CLAUDE.md on the touched files:
   `backend-endpoint-reviewer`, and `migration-reviewer` for the renamed migration.
3. Fix the findings in the #671 branch. Nothing gets waived.

**Exit:** no open BLOCKER findings.

## Phase D: local validation and push

1. **Run `Verify-Local-CI.ps1`** with no `ANTHROPIC_API_KEY`. Every lane must be green,
   including:
   - the NL-filter offline lane, with `drift == {}`;
   - the tenant-safety and AI-context tests;
   - the Alembic tests.
2. **Check the deterministic guarantees #671 depends on**, adding any that are missing:
   - policy unavailable → 403 `project_ai_policy_unavailable`, before any provider call;
   - policy `help_only` → 403 `project_ai_policy_disabled`, before any provider call;
   - `model_data` → reaches the model adapter;
   - `prompt_sha256` is unchanged.
3. **Push** through `Push-And-Verify.ps1` with a force-with-lease, because this is a rebase.

**Exit:** #671 is MERGEABLE and its remote checks are green.

## Phase E: merge

This needs separate owner authorization. It is not implied by this plan.

---

## Guardrails that apply to every phase

- No `ANTHROPIC_API_KEY` and no paid call, except under path (b) by the owner's choice.
- No lowered threshold, no `continue-on-error`, no silent external fallback.
- Don't auto-resolve the tenant conflicts.
- Don't enable `BIMPOSSIBLE_AUTODESK_FIRST_ACCESS`.
- No edits to the queue, wave ledger or PHASE-STATUS.
- One worktree per session, and never work in a tree another session is using.

## Out of this plan

- **The local-model behavioural lane.** It is on the AI-Server roadmap: a local-provider
  runner with evidence schema v2, never labelled as Haiku evidence. It needs its own scope
  first.
- **A general fingerprint redesign beyond the NL-filter monitor.**
