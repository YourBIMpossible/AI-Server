---
status: active
---

# Mission: AI-Server — one measurable local inference endpoint

> Drafted 2026-09-10 alongside `decisions/2026-09-10__box-build-reassessment.md`. Revised
> 2026-09-11, when the client contract was decoupled from Ollama and the runner became an
> open question settled by `handoffs/WP-H_runner-bakeoff.md` rather than by inertia.
>
> **Locked and human-only by default.** `protect_paths_gate` blocks assistant Write/Edit on
> this path, and the assistant does not route around it. The owner can grant permission for
> a specific change; absent that, propose changes as `NORTHSTAR.draft.md`.

## Mission

Stand up and keep one dedicated, headless, always-on, **OpenAI-compatible** local inference
endpoint that internal tooling can rely on — and make local-model performance **measurable**,
so decisions about what to run locally are settled by evidence rather than by vibes or by a
blog post.

The mission is the *endpoint*, not the program serving it. Ollama is the initial baseline
runner and nothing more; it has not won anything yet. Clients know three settings —
`INFERENCE_BASE_URL`, `INFERENCE_API_KEY`, `INFERENCE_MODEL` — and no runner name appears in
application code, config keys, or automations.

## Why this framing, and not the old one

The June 2026 plan justified this box as product infrastructure: on-device RAG for
BIMpossible customers. That justification is gone — the owner ruled on 2026-07-27 that
local models "will not land with real clients or their hardware," and the slice that would
have consumed it is deferred behind a named air-gapped customer.

What replaced it is narrower and better-evidenced. Every headline failure measured on the
5080 rig — 66% model residency, 56–75s cold loads, a workhorse model missing its latency
gate — is a *shared Windows desktop* failure, not a model failure. A headless Linux box
with a dedicated GPU fixes them structurally. And because a dedicated box has a **stable
hardware profile**, it's the only place local-model measurements stay valid long enough to
decide anything.

The box is not "more VRAM for bigger models." It's the instrument.

## What done looks like

- The endpoint is up, survives reboot, and serves an OpenAI-compatible API over Tailscale
  with the serving layer correctly configured — **verified from the server's own startup
  banner**, not from a shell.
- Phase 0 has been re-run on the box, and the three open questions are answered with
  numbers: does 30B-A3B go fully resident at 32k, does Linux `mmap` kill the cold-load
  penalty, does the 14B clear its 20s gate without desktop VRAM contention.
- At least one real automation runs unattended against it and clears the WP-F bar — where
  WP-F scores **semantics, not just schema validity**.
- Model choice is a config line backed by an eval score, not a name copied out of a doc.
- The runner has been chosen by the WP-H bakeoff, not by whichever one got installed first —
  and swapping it is provably a deployment change, demonstrated by the full WP-F workload plus
  one unattended real automation passing against the replacement. `/v1/models` answering is
  not acceptance.

## Off-limits

- **No public exposure.** LAN/Tailscale only. Never port-forward 11434.
- **No client data on this box** until the OCR hard stop of 2026-08-24 is resolved on its
  own terms. That's a separate decision with its own gate.
- **No runner declared permanent without winning the bakeoff.** That cuts both ways: Ollama
  doesn't get to stay by default, and llama.cpp doesn't get adopted on reputation. vLLM is
  excluded on a specific technical reading — Ampere has no FP8 hardware and the workload is
  single-user, so continuous batching has nothing to bite on. If either of those stops being
  true, that exclusion is void and vLLM re-enters the bakeoff like anything else.
- **No runner name in client code, config keys, or automations.** Ollama-native calls live
  only in `scripts/` ops tooling, as enrichment that degrades cleanly.
- **No porting the rig's numbers.** Hardware profile is part of batch identity; every
  measurement taken on the 5080 is void here. Re-measure.
- **Not a desktop.** The moment this box runs a game or Revit, it stops being the thing
  that makes measurements valid.

## Explicitly out of scope

Customer-facing local inference (owner-deferred, demand-gated), a bigger embedding model
(no consumer — both shipped retrieval paths chose BM25), and rescuing the GPU OCR service
(hard-stopped on security, needs its own review).
