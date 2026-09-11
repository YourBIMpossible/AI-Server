# WP-H — Runner bakeoff: Ollama vs llama.cpp

**Goal:** settle which program serves the endpoint, on evidence, once — instead of letting the
first thing installed become the standard by default.
**Depends on:** the box operational; WP-F eval harness; Phase 0 re-run on the box.
**Status:** not started. Ollama is the **initial baseline**, not the decision.

---

## Why this exists

The requirement is *a private, stable, OpenAI-compatible local inference endpoint*. Ollama is
one implementation of that requirement. The earlier plan let Ollama feel inevitable because it
happened to be the carrier for the serving-layer fixes that actually mattered (flash attention,
context length, keep-alive) — those are wins for the *configuration*, not evidence for the
*runner*.

Nothing here is an argument that Ollama is wrong. It may well win. The point is that it has to.

**vLLM is out of this bakeoff** on a specific technical reading, not a preference: Ampere
(RTX 3090) has no FP8 hardware, and the workload is single-user, so continuous batching has
nothing to bite on. If either of those changes, that exclusion is void.

---

## Run the test fair, or don't run it

Hold these identical across both runners, or the numbers mean nothing:

- **The same model artifact** — the same GGUF file on disk, not "the same model name" from two
  different registries.
- **The same quantization.**
- **The same context length** (32768) and the same KV cache dtype.
- **The same prompt corpus**, drawn from the real workload — prefill-dominated, 27K–32K tokens.
- **The same warm/cold protocol**: define cold (process just started, nothing in page cache)
  and warm (model resident, `keep_alive` honored) explicitly, and measure each separately.
- **The same semantic evaluator** — the WP-F grader, unchanged, scoring meaning rather than
  schema validity.
- **The same hardware, same session.** Hardware profile is part of batch identity. Do not
  compare a number taken today against one taken before a driver update.

---

## What to measure

Performance:

| Metric | Notes |
|---|---|
| Startup / restart reliability | Does it come back clean, every time, unattended? |
| Model loading + cold-load time | The 56–75s Windows figure was an mmap artifact; re-measure on Linux |
| TTFT at 27K–32K prompt | The metric that actually governs the workload |
| Prefill throughput | The dominant cost here. Optimize this, not decode |
| Decode throughput | Secondary, but record it |
| Peak VRAM | At full context, with the KV cache populated |

Correctness:

| Metric | Notes |
|---|---|
| Tool-call behavior | Real `tool_calls` array, not a tool call rendered as prose |
| JSON-schema constrained generation | Does constraint actually constrain, or is it advisory? |
| Semantic WP-F score | Same evaluator, same cases, same threshold |

Operational:

| Metric | Notes |
|---|---|
| Behavior after reboot | Not "does the service start" — does the *endpoint serve* |
| Behavior after an unattended scheduled job | The real failure mode: works when watched |
| Remote OpenAI-client compatibility | From the rig, over Tailscale, through the auth gateway |
| Model updates, rollbacks | How much ceremony to change a model, and to undo it |
| Logs and observability | Can you tell *why* a slow request was slow? |
| systemd management | Env that survives restart, verified from the startup banner |

---

## Portability is a gate, not a promise

**`/v1/models` responding is not acceptance.** "OpenAI-compatible" is a claim about a URL
shape, and it says nothing about equivalence in:

1. chat-template behavior
2. tool-call serialization
3. JSON-schema constrained generation
4. streaming semantics
5. embedding endpoints
6. tokenization and context accounting
7. model aliasing and loaded-model behavior
8. error and retry behavior

Any one of those can differ silently — the endpoint answers, the automation runs, the output is
subtly wrong, and nothing fails loudly.

**Migration acceptance test** — a runner is only adopted when, against *it*:

- the full WP-F workload passes at threshold, semantically scored; **and**
- at least one **real automation runs unattended, on its own schedule**, start to finish,
  and its output is correct.

Both, on the replacement runner, before anything is called permanent.

---

## Deliverables

- `eval/bakeoff/protocol.md` — the frozen protocol: model artifact hash, quant, context length,
  corpus, cold/warm definitions, hardware profile, date. Written *before* the first measurement.
- `eval/bakeoff/run.py` — drives both endpoints through the same cases via
  `aiserver.client.LLM` (no runner-native calls in the harness itself); emits raw per-request
  timings, not just averages.
- `out/bakeoff/report-YYYY-MM-DD.md` — the metric tables above, both runners side by side, with
  the hardware profile stamped in. Percentiles, not just means; TTFT distribution matters more
  than its average.
- A decision entry in `decisions/` recording the winner, the margin, and **what would reverse
  it** — so the next person doesn't have to re-derive whether it's still true.

## Acceptance

- Both runners measured under the frozen protocol, same session, same hardware.
- The migration acceptance test above is run against the challenger, and its result recorded
  whether it passed or not.
- The decision doc names the losing runner's advantages honestly. If it's close, say it's close.

## Constraints

- **Endpoint security unchanged:** LAN/Tailscale only, never a public bind, during the bakeoff
  too. A test rig is not an exception.
- No client data in the corpus — the OCR hard stop of 2026-08-24 is unresolved.
- Outputs under `out/` (gitignored); the protocol and the decision are repo artifacts.
- Don't port numbers from the 5080 rig into this report as a comparison row. They were measured
  on different hardware under a different OS and they are void here.
