# Review: MyBuddy complete strategy (2026-09-21)

**Reviewed:** `mybuddy-complete-strategy-rationale-and-implementation-review.md`, supplied by the owner.
**Checked against:** `NORTHSTAR.md`, `CLAUDE.md`, live box state (2026-09-21), `F:\Local Intel`.

**Verdict:** the direction is coherent, and the order it puts things in is mostly right. It is
a **different mission** from the one locked in `NORTHSTAR.md`, though. As written, it can't be
worked under the current north star. Priorities 0–2 fit today. Priorities 3–9 need a new
mission file. Priority 8 should be cut.

## Blockers (must resolve before building past Priority 2)

1. **Mission mismatch.**
   - NORTHSTAR's mission is "one measurable local inference endpoint." Its own words: "The box
     is not 'more VRAM for bigger models.' It's the instrument."
   - The strategy makes the box a platform: control plane, task queue, memory, agents, tools.
   - That's a legitimate new direction, but only the owner can activate it. Draft it as
     `NORTHSTAR.<slug>.draft.md` and rename it to activate, or amend `NORTHSTAR.md` yourself.
   - Until then, Priorities 3–9 are roadmap, not work.
2. **"No external LLM calls" conflicts with routes C and D.**
   - `CLAUDE.md` says the target box is "fully local, no external LLM calls." The strategy's
     cloud-escalation routes contradict that.
   - Workable split: the box never calls out. Any cloud route is run by a worker on the rig,
     and labeled in the task record (the strategy already says "no invisible cloud fallback").
   - Write that split down explicitly. Otherwise the first router implementation will put the
     cloud call on the box.
3. **"No client data on this box" (NORTHSTAR off-limits).**
   - Several of the strategy's domains will carry client data: Revit models, meeting
     transcripts, email, Slack and Teams.
   - That off-limits line is tied to the 2026-08-24 OCR hard stop, which has its own gate.
   - The Knowledge/Memory Charter (P3) and P6/P9 must say where client-derived material lives.
     Either it stays on the rig, or that gate is resolved first.

## Cut or reframe

4. **Priority 8 (browser/subscription worker): recommend reject, not "experiment."**
   - The consumer terms of the major chat subscriptions generally prohibit automated or
     scripted access. Breaking them risks losing the account you're trying to leverage.
   - The doc already concedes stability and terms problems. The honest outcome of the
     "evaluation" is predictable.
   - If external capability is needed, use the official APIs (billed), or Claude Code itself
     as the named route.
   - Quick hack being rejected: driving a logged-in Chrome profile against a chat site.
5. **Priority 0 (inventory) is unbounded.**
   - "Inventory everything" across 9+ repos can eat weeks and produce a stale document.
   - Time-box it to the assets P1/P2 actually touch: `local-intel`, `evidence-compiler`, and
     the Claude Code hook path in `claude-profile`.
   - Map the Revit/BIMpossible assets when P6 starts, not before. `/next` already holds
     cross-repo status; reuse it rather than writing a parallel map.

## Corrections of fact / overclaims

6. **Gemma's 27/27 is not evidence it can offload Claude work.**
   - That score comes from a small personal chat scoring set.
   - P1 must measure against the actual task classes (log triage, repo summary, context
     brief). The doc implies the model is "measured and retained" for that purpose; it's only
     measured for chat.
7. **One GPU, one queue.**
   - The box runs Ollama with `NUM_PARALLEL=1` and `MAX_LOADED_MODELS=2`. Overnight agent work
     and interactive chat share one request queue.
   - Any second model a UI or agent asks for evicts or crowds gemma4.
   - "Keep all three UIs" (Part II §4) is fine only if all three stay pinned to the same model.
   - P5/P7 need a rule about who wins the GPU at night.
8. **The rig's 5080 isn't an always-on worker.**
   - P7 routes vision, voice and Revit work to it. It is the desktop you use, so it's only
     available when you are.
   - Rig-side work needs a "worker unavailable → queue, don't fail" state.
9. **"Existing Whisper workflow" is unverified here.**
   - No record of it exists in AI-Server. Confirm where it lives before P9 leans on it.

## Missing

10. **A baseline for the money question.**
    - "Reduce Claude Code usage" has no number. Before P1, capture one to two weeks of current
      spend or usage by task class; otherwise savings can't be shown.
    - Success metric suggestion: X% of prompts in class Y handled locally, with a validator
      pass rate of at least Z and no rise in rework.
11. **Authority and security model for agents.**
    - The personal plan's "revisit the bigger design" tripwire fires the moment an agent gets
      write or exec authority. OpenCode already trips it (see
      `reviews/2026-09-21__opencode-setup-review.md`).
    - The strategy mentions permissions only as review questions. It needs a concrete default
      before P4: worktree-only writes, ask-before-exec, no network egress from the box, and
      key via env var.
12. **Backups before write-capable workflows.**
    - The UI data volumes are not backed up today, and the strategy's task artifacts and memory
      will be the valuable part.
    - Add a backup step as a P3 prerequisite, not a review question.
13. **Endpoint contract for consumers.**
    - `local-intel` has `ollama_client.py`. That's acceptable inside its own repo, but when it
      runs against MyBuddy it should go through the gateway via
      `INFERENCE_BASE_URL`/`INFERENCE_API_KEY`, not raw 11434. That keeps the WP-H runner
      swap a deployment change.

## Fine as written

- "Work first, hardware second"; vertical slices; the promotion ladder (three validated runs
  with less cleanup than doing it by hand); explicit routing rules before learned routing.
- Reconcile existing assets instead of rebuilding them.
- **P1 is the best next step, and it serves the current NORTHSTAR directly.** Running
  `local-intel` unattended against the box is exactly "one real automation clears the WP-F
  bar."
- Fail-open adapter design for P2.
- P10: no new hardware without measured bottlenecks.
- Corporate systems only through approved routes.

## Suggested order

P1 (with the baseline from #10) → P2 → owner writes the new north star → P3 with backups →
P4 → P5 → P6 → P7 → P9. Drop P8. P0 is folded into P1/P2 as a scoped inventory.

## Your call

- Activate the platform mission as a new north star (and whether it replaces or sits beside
  the endpoint mission).
- The cloud-route location rule (#2) and the client-data location rule (#3).
- Keep or drop P8.
