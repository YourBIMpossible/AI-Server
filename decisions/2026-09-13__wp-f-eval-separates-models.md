# WP-F — the eval now separates models

**Date:** 2026-09-13 · **Box:** `mybuddy-3090-02` · **Branch:** `box-mission`
**Status:** evidence only. No model is picked and `config/models.txt` is untouched (owner's call).

## TL;DR

- Before: every model scored 17/17. Now, on 27 cases (the 17 old + 6 hard + 4 long at 21–27k tokens), the six candidates score **22–27**.
- The two coder models fail 5 (qwen3-coder 30B-A3B, 22/27) and 4 (qwen2.5-coder 14B, 23/27) of the hard and long items. gemma4 26B-A4B, qwen3.8 27B and nemotron-3.5 30B-A3B score 27/27; gemma4 31B scores 26/27.
- **The top of the scale is saturated.** The eval now separates the coder models from the rest, but it cannot rank gemma4 26B vs qwen3.8 vs nemotron. That needs harder cases, or a latency and residency tie-break.
- **The local judge is not trustworthy on its own.** It false-failed a correct paraphrase twice. It is now used on one case only, is calibrated on every run, and cannot rescue a keyword miss.
- **Found on the way:** an Ollama prompt over 32,768 tokens is **silently cut to ~16,386**, not rejected. gemma4's Phase 0 driver runs show exactly that count, so they were most likely truncated (not re-tokenized to confirm).

## What changed (commits on `box-mission`)

| Commit | Change |
|---|---|
| `3d14155` | Reasoning stripping (`<think>`/`<thinking>`/`<reasoning>`; an unterminated tag strips to end, which counts as a miss). Exact-format gates (`regex_full`, `json_equals`, `max_words`) and graded `patterns`. Optional judge (temperature 0, seed 0). 10 new cases. An errored case scores 0 instead of aborting the run. |
| `e46bc50` | Judge prompt: grade meaning, not wording |
| `17c1776` | Judge calibration set (8 answers with known verdicts; agreement stamped on every report). `eval.rescore` re-grades saved answers without re-asking the model. `LLM.chat_timed` for WP-H. |

`python -m pytest`: all tests pass against the stdlib mock (no real runner).

### The new cases

| Tier | Case | What a weaker model does |
|---|---|---|
| hard | `digest-constraints` | ignores one of four constraints (sentence count, word cap, owner, forbidden topic) |
| hard | `rag-distractor-port` | answers the deprecated port, or explains instead of answering |
| hard | `rag-refuse-nearmiss` | gives the Q3 *forecast* as the actual revenue |
| hard | `extract-iso-dates` | keeps duplicates written in a different format |
| hard | `classify-root-cause` | calls a disk-full cascade an `environment_failure` |
| hard | `reasoning-business-days` | mis-counts around a holiday |
| long | `long-digest-ops` (27.0k tok) | miscounts failed prod deploys among staging, CI and neighbouring-day decoys |
| long | `long-gate-deploy` (27.0k) | says YES for a deploy that started on the 20th but completed on the 21st, or for a cancelled or failed one |
| long | `long-extract-worker-errors` (26.0k) | lets WARN, wrong-service or wrong-code decoys into the list |
| long | `long-rag-retention` (20.8k) | quotes the superseded 90-day ADR |

- **Long documents:** deterministic and synthetic (`eval/longinputs.py`), no client data. Every graded fact is planted, and tests prove filler can never produce one.
- **Sizes:** calibrated on the Qwen and Gemma tokenizers to stay under 32,768 with room to answer (see the truncation finding).

## Results

Answers at temperature 0 via `/v1/chat/completions`. Judge: `qwen3-coder:30b-a3b-q4_K_M` for every model. Numbers are after `eval.rescore` under the final grader.

| Model | Pass /27 | basic /17 | hard /6 | long /4 | Failed cases | Long-case median s |
|---|---|---|---|---|---|---|
| gemma4:26b-a4b-it-q4_K_M | **27** | 17 | 6 | 4 | — | 25.5 |
| qwen3.8:27b-q4_K_M | **27** | 17 | 6 | 4 | — | 44.3 |
| nemotron-3.5-lightning:30b-a3b-q4_K_M | **27** | 17 | 6 | 4 | — | 37.7 |
| gemma4:31b-it-q4_K_M | 26 | 17 | 6 | 3 | long-extract-worker-errors (dropped one id) | 56.5 |
| qwen2.5-coder:14b | 23 | 17 | 5 | 1 | reasoning-business-days, long-digest-ops, long-gate-deploy, long-extract-worker-errors | 15.3 |
| qwen3-coder:30b-a3b-q4_K_M | 22 | 17 | 4 | 1 | extract-iso-dates, reasoning-business-days, long-digest-ops, long-gate-deploy, long-extract-worker-errors | 9.8 |

The original 17 basic cases: every model 17/17, as before.

**Judge calibration: 6/8 for `qwen3-coder:30b-a3b`.** Both misses are false FAILs on correct answers (`cal-paraphrase-pass`, `cal-two-sentences-pass`). It passed no wrong answer: the retention, wrong-person and empty cases were all right. The judge fails too often rather than passing too easily. A judged PASS is therefore the more trustworthy verdict, and the one judged case (`long-rag-retention`) passed for every model.

Per-case failures, raw outputs and calibration: `out/eval-runs/<model>/eval/` (gitignored).

## Findings

1. **Separation is real but shallow.**
   - **Coder models:** qwen3-coder 30B-A3B and qwen2.5-coder 14B fail the counting, gating and exclusion items that depend on long context, plus business-day arithmetic.
   - **Thinking and general models:** they pass them. Thinking tokens go to the `reasoning` field on Ollama's `/v1`, so they never pollute `content`.
   - **The earlier contradiction explained:** Phase 0 scored the thinking models "unparseable" through the native API. On the OpenAI-compatible surface they are correct.
2. **Ceiling.** Three models at 27/27 means these cases can certify "good enough", but they cannot rank the top three. The next discriminators are latency (qwen3.8 and nemotron reason for tens of seconds per long case), residency (gemma4 31B and nemotron do not fit fully at 32k, per the Phase 0 remeasure), and harder cases.
3. **The judge is the weak link.**
   - **What happened:** `qwen3-coder` answered "FAIL — does not attribute the revert to Marco; it says 'reverted by Marco'".
   - **Response:** the judge now sits on one case whose keyword gates already hold the ground truth, and every run stamps calibration agreement.
   - **Rule:** a judged verdict never turns a keyword miss into a pass.
4. **Silent truncation.** An oversized prompt returned `prompt_tokens: 16386` with HTTP 200. gemma4's Phase 0 runs report 16,387 prompt tokens on a fixture the Qwen tokenizer counts at ~27.3k. Treat gemma4's Phase 0 numbers as measured on half the input. *Not yet re-tokenized to confirm.* The WP-H oversize probe measures this behaviour per runner.

## Not done / flags

- **Claude baseline:** skipped (no `ANTHROPIC_API_KEY` on the box). The routing table is local-only.
- **Model pick:** the owner's. Per the protocol, WP-H uses the non-thinking `qwen3-coder:30b-a3b` artifact as a fixed test object, not as a recommendation.
- **Scope flag:** 3–5 harder long cases (multi-hop across two documents, contradictory updates, arithmetic over extracted values) would separate the top three.
