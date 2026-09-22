# Personal-AI workspace handoff routed (2026-09-21)

**Source (imported verbatim):** `handoffs/PERSONAL-AI-HANDOFF-2026-09-21.md`, written by a
separate chat session, checked against this repo (NORTHSTAR.md, WORKLOG.md, `decisions/`).

Part 1 (the BIMpossible PR #671 CI-plan decision) was moved to the private BIMpossible repo on
2026-09-21: it describes private security work and this repo is public. PR #671 (private BIMpossible) is planned in that repo: `docs/plans/2026-09-21__pr671-resolution-plan.md`.

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
| Open WebUI as a private cockpit through `:11440/v1` | **Already accounted for** | Existing UI-placement call (a/b), LibreChat endpoint, one-click launcher |
| Model scorecard / test corpus | **Already accounted for** | Roadmap "Score the four unevaluated models" |
| Goose on the **rig** in a disposable worktree | **Changed existing item.** Moves off the box, which removes the "instrument" objection. Still a new subsystem | WORKLOG → the existing Goose item is amended |
| RAG source governance before any ingest | **Added to the roadmap.** Real gap: `config/rag_sources.txt` declares two broad roots and no exclusion or citation rule exists | Roadmap |
| Cloud provider / routing policy | **Part of the scope-split draft.** Outside the endpoint mission ("fully local, no external LLM calls") | Goes into the draft if one is written |
| MCP / tool authority policy | **Part of the scope-split draft** | Same |
| vLLM criterion | **Already accounted for.** NORTHSTAR off-limits and CLAUDE.md ("not planned") | — |
| Python 3.14 has no pip | **Already accounted for** | Memory and `decisions/2026-09-13__box-phase0-remeasure.md` |
| UI hosting and storage model | **Folded into the existing UI-placement call (a/b)** | WORKLOG |

**Net:** one roadmap addition (RAG source governance), one amended call (Goose → rig), one
reopened call (`:11434`), and one new call (scope split). Everything else is already covered.
