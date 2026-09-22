# Two handoffs routed: personal-AI workspace, and the local-AI CI plan for BIMpossible PR #671 (2026-09-21)

**Sources (imported verbatim):** `handoffs/PERSONAL-AI-HANDOFF-2026-09-21.md`,
`handoffs/LOCAL-AI-CI-PLAN-PR671-2026-09-21.md`. Both were written by separate chat sessions.
**Method:** checked against this repo (NORTHSTAR.md, WORKLOG.md, `decisions/`) and, for
#671, against BIMpossible `main` (`198f0a94`) and the PR head (`395d138f`). The PR head was
extracted with `git archive` into a scratch directory, and the NL-filter monitor and its
tests were run there. No BIMpossible checkout, branch or PR was modified, and no provider
call was made.

---

## Part 1 — PR #671: the local-AI CI plan

### Decision

**Against the plan as the way to unblock #671. For one narrow slice of it, as a small
BIMpossible PR of its own.** The local runner (plan Phase 3) goes to the roadmap as a
cross-repo item. It is not on #671's path.

### What actually blocks #671

I measured this, not relying on what the plan claims:

| Check on the PR head `395d138f` | Result |
|---|---|
| `nl_filter_monitor.py --mode offline` (the Verify-Local-CI lane) | **PASS**: score 1.0, `drift=nl_filter_source_sha256`, exit 0 |
| `prompt_sha256` | **unchanged**. The model-facing prompt did not move |
| `pytest tests/eval/test_nl_filter_monitor.py` | **3 failed / 36 passed** |

The three failures:

- `test_no_drift_against_the_checked_in_baseline`. The committed baseline no longer
  describes the tree, because #671 edits `backend/aec/nl_filter.py`. That edit adds a
  pre-model fail-closed branch, `PROJECT_AI_POLICY_UNAVAILABLE`, plus
  `lookup_ai_context_policy`.
- `test_pin_drift_is_reported_but_does_not_fail` and
  `test_a_pin_missing_from_the_baseline_is_reported_as_drift`. These assert an exact
  `drift` dict. The ambient source-hash drift adds a second key to it.

So the plan's premise is half right:

- **Right:** the gate is a false positive. Only the whole-file source hash moved, and that
  pin "deliberately over-reports".
- **Wrong:** where the gate lives. It is not the offline lane, which reports drift and never
  fails on it (`docs/CI-GATES.md` § "Drift is reported, never failed"). It is the backend
  pytest suite, whose failure message says to re-run `--mode live --repeats 10` and then
  `--write-baseline`. That live run is the paid Haiku call.

### Why the local runner is not the #671 fix

1. **It measures a different model.** The pinned model is `claude-haiku-4-5`, which is what
   production calls. Local gemma or qwen evidence says nothing about Haiku's behaviour on
   declines or prompt injection. The plan's own §6.3 says local evidence must never stand in
   for provider evidence. So after it is built, #671 still has no Haiku evidence. It has only
   had its requirement removed.
2. **It is not needed.** Once the source hash is demoted to provenance, #671 needs no
   behavioural evidence at all, from any provider. That is the plan's own "authorization-only"
   rule (Phase 4). Phases 3 and 6 add nothing to #671.
3. **It is a feature, not a fix.** It adds a provider interface, an evidence schema v2, a
   local runner, and a new consumer of `mybuddy` (BIMpossible CI). That spans two repos, and
   none of it is in either repo's current mission.

### The narrow slice that does unblock it: a separate BIMpossible PR to `main`

- **Split the pins.** `nl_filter_source_sha256` becomes provenance only: it is recorded,
  printed, and excluded from `drift`.
- **Add a pin that fills the hole this opens.** The whole-file hash currently also covers
  things outside the prompt template literal: sampling and token config, response parsing,
  and the grounding vocabulary cap. Add a `model_config_sha256` pin, or an equivalently
  narrow one, over the model-facing call parameters. Without it the demotion is a real
  weakening, not a correction.
- **Keep what does not change.** Thresholds, the live half, the 14-day staleness report and
  the stale-marking on re-pin all stay as they are.
- **Fix the two exact-dict tests** so that they don't depend on ambient drift.
- **Test it.** Deterministic tests only. Verify-Local-CI stays keyless.

Then #671 rebases onto it. After the rebase, the drift is gone and no re-pin or live run is
needed. Cost: $0, and about a day of work. This is a change to CI policy in BIMpossible, which
is the owner's call, and that is why it is proposed here rather than built.

**The quick hack, named so you can reject it:** run `--write-baseline` on #671 itself. The
pytest turns green, and the live evidence is marked `stale` with `pins_at_recording` kept.
It is honest on disk, but `CLAUDE.md:53` forbids "`--update-baseline` to unblock", and this is
that move with a paper trail. Not recommended.

### #671's real blockers, which the plan correctly leaves out of scope

1. **Tenant-isolation conflicts** against `main` in `cross_firm_sharing.py`,
   `hub_tenancy.py` and `router.py`. The PR is CONFLICTING/DIRTY. The fix is a manual rebase
   followed by a security-engineer review of the resolved hunks. It must not be auto-resolved.
2. **The migration rename** `e5f6a7b8c9d1 → a4c1e9b73f52` exists only in the local commit
   `07731a4d`, which is unpushed. It does not depend on the NL-filter question, so it can be
   pushed through `Push-And-Verify.ps1` now or with the rebase.

**Order:** pin-split PR → rebase #671 (security-reviewed conflicts, plus `07731a4d`) → full
Verify-Local-CI with no key → push → separate merge authorization.

---

## Part 2 — Personal-AI workspace handoff: routing

### Errors in the handoff (the repo wins)

- **"NORTHSTAR.draft.md, not locked."** Wrong. `NORTHSTAR.md` is active and locked, and
  closeout on 2026-09-13 met all five criteria (PR #20). No draft exists.
- **gemma4:26b called the "personal OCR production candidate."** It is the endpoint's
  `INFERENCE_MODEL` pick (27/27). Personal-OCR is a separate project.
- **`:11434` treated as open.** It is a settled call: `--enforce` stays off per the
  runner-pick decision, and the closeout accepted it. See the item under Needs your call.

### Item by item

| Handoff item | Route | Where |
|---|---|---|
| Scope split: `mybuddy` as infrastructure plus a separate "Personal AI Workspace" | **Needs your call.** Consistent with the mission ("a consumer of the endpoint") | WORKLOG → needs a `NORTHSTAR.personal-ai.draft.md` if yes |
| NORTHSTAR edit or lock | **Rejected as framed.** Already locked; changes are human-only | — |
| Raw `:11434` restrict or rebind | **Settled; the owner may reopen.** New fact: three UIs now run | WORKLOG → Needs your call |
| Open WebUI as a private cockpit through `:11440/v1` | **Already accounted for** | Existing pilot call (a/b), LibreChat endpoint, one-click launcher |
| Model scorecard / test corpus | **Already accounted for** | Roadmap "Score the four unevaluated models" |
| Goose on the **rig** in a disposable worktree | **Changed existing item.** Moves off the box, which removes the "instrument" objection. Still a new subsystem | WORKLOG → the existing Goose item is amended |
| RAG source governance before any ingest | **Added to the roadmap.** Real gap: `config/rag_sources.txt` declares two broad roots and no exclusion or citation rule exists | Roadmap |
| Cloud provider / routing policy | **Part of the scope-split draft.** Outside the endpoint mission ("fully local, no external LLM calls") | Goes into the draft if one is written |
| MCP / tool authority policy | **Part of the scope-split draft** | Same |
| vLLM criterion | **Already accounted for.** NORTHSTAR off-limits and CLAUDE.md ("not planned") | — |
| Python 3.14 has no pip | **Already accounted for** | Memory and `decisions/2026-09-13__box-phase0-remeasure.md` |
| UI hosting and storage model | **Folded into the existing pilot call (a/b)** | WORKLOG |

**Net:** one roadmap addition (RAG source governance), one amended call (Goose → rig), one
reopened call (`:11434`), and one new call (scope split). Everything else is already covered.
