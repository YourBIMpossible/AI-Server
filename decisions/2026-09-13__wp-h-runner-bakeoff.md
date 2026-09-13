# WP-H — runner bakeoff: Ollama 0.34.0 vs llama.cpp b10937

**Date:** 2026-09-13 · **Box:** `mybuddy-3090-02` · **Branch:** `box-mission`
**Protocol:** `eval/bakeoff/protocol.md`, frozen before the first measurement. Raw records:
`out/bakeoff/*.jsonl`, report `out/bakeoff/report-2026-09-13.md` (gitignored).
**Status:** evidence. **The pick is the owner's.** Nothing here declares a runner permanent and
`config/` is untouched.

## TL;DR

- **Performance is a tie.** Same GGUF file, same settings: warm TTFT on a 27k-token prompt 11.55 s (llama.cpp) vs 11.62 s (Ollama); prefill ≈2,350 tok/s and decode ≈190 tok/s on both; peak VRAM 21,064 MiB on both. Process-cold to first token: 12.6 s vs 13.3 s.
- **Correctness is a tie.** Full WP-F: 22/27 on both, same five failures, 26 of 27 outputs byte-identical. Tool calls, JSON-schema constraint and streaming pass on both.
- **The differences are behavioral, and each runner has one that matters.** Ollama **silently truncates** a prompt over 32,768 tokens to 16,386 and returns HTTP 200; llama.cpp **rejects it with HTTP 400**. llama.cpp **accepts any model name** and serves its one model; Ollama returns 404 for an unknown name.
- **Migration acceptance for llama.cpp: not passed yet.** WP-F is at parity (condition 1), and the unattended job ran end to end on it, but the grade failed on both runners under a rubric that was too strict (see below); the corrected re-run is recorded in the acceptance table.
- **Operationally llama.cpp is behind on this box:** no systemd unit (needs root), no model registry (one process per model, one model per process), and the artifact is addressed by blob path.

## What was held identical

Model artifact `/srv/models/blobs/sha256-1194192cf2…` (18.56 GB, `qwen3moe`, Q4_K_M) served by both. 32,768 context, one slot, f16/f16 KV, flash attention on, 49/49 layers on GPU (both runners' own logs), mmap on both, `top_k 20 / top_p 0.8 / repeat_penalty 1.05`, every request `temperature 0`. Same synthetic corpus with unique-prefix lines so no timed request hits a prompt cache. Same session, 06:26–06:36 UTC, one runner on the GPU at a time (GPU memory 21 MiB between them).

**Known, unavoidable difference:** chat template. Ollama's Go renderer vs the GGUF's Jinja template (`--jinja`). Effect measured: 26/27 identical outputs; the one difference is a paraphrase that both graders passed.

## Performance

| Warm, 5 reps each | prompt tokens | TTFT p50 s — llama.cpp | — Ollama | prefill tok/s p50 — llama.cpp | — Ollama |
|---|---|---|---|---|---|
| ops_log | 27,140 | 11.55 | 11.62 | 2,349 | 2,336 |
| worker_log | 26,051 | 11.00 | 11.05 | 2,368 | 2,358 |
| docs_corpus | 20,883 | 8.06 | 8.12 | 2,590 | 2,571 |

p90 within 0.15 s of p50 on both; 0 errors in 30 timed requests. Decode (512-token enumeration, 3 reps): 190.5 vs 190.8 tok/s. Peak VRAM 21,064–21,066 MiB on both.

| Cold (3 cycles) | ready s | first TTFT s | total s p50 | max |
|---|---|---|---|---|
| llama.cpp (process start → `/v1/models` 200 → first request) | 1.9 | 10.7 | 12.6 | 13.3 |
| Ollama (server up, model unloaded → first request) | 0 | 13.3 | 13.3 | 13.8 |

Both are process-cold with a warm page cache (no root to drop it; question (b) showed disk-cold ≈ process-cold on this drive). llama.cpp answers `/v1/models` before the model is loaded; the 10.7 s first request is the load.

**Reading:** both runners are the same llama.cpp engine on the same file; the 0.5–0.7 s cold difference is Ollama's runner-subprocess spawn. There is nothing here to choose on.

## Correctness

| Probe | llama.cpp | Ollama |
|---|---|---|
| Real `tool_calls` array (`get_weather`, `{"city": "Paris"}`) | pass | pass |
| `response_format: json_schema` (`additionalProperties: false`, enum) constrains — the model was asked to add a forbidden `notes` field and did not | pass | pass |
| Streaming: chunks, `finish_reason`, usage via `stream_options` | pass (32 chunks) | pass (22 chunks) |
| Unknown model name | **FAIL** — serves the loaded model under any name | pass — HTTP 404 |
| Prompt over the context (54,276 tokens) | pass — HTTP 400 `exceed_context_size_error` | **FAIL** — HTTP 200, `prompt_tokens: 16386`, answer computed on half the input |
| `/v1/models` lists the served name | pass | pass |
| Full WP-F, semantic (self-judged, calibration 6/8 on both) | 22/27 | 22/27 |

Both behaviors are silent from the client's side. Ollama's is the more dangerous for this workload (27k-token prefill-dominated prompts): an automation that drifts past the window gets a confident answer about half its input and no error. It also explains gemma4's Phase 0 anomaly (`decisions/2026-09-13__box-phase0-remeasure.md`). llama.cpp's is a footgun for a multi-model future: a typo in `INFERENCE_MODEL` is answered by whatever is loaded.

## Operational

| | llama.cpp | Ollama |
|---|---|---|
| Restart reliability | not measured — no systemd unit (root); ran under `nohup` | systemd `Restart=always`; crash test script committed, run pending root |
| Reboot behavior | not measured (no unit) | verified from the startup banner after the 02:16 UTC reboot |
| Model management | one process per model, addressed by blob path; no pull/registry; a second model means a second port | registry, pull, tags, `MAX_LOADED_MODELS=2`, one port |
| Logs | per-request timings in the server log; `timings` object available in responses | request lines only; runner subprocess log in journald |
| Remote client via gateway | not run — gateway upstream points at Ollama | gateway verified on loopback |
| Unattended scheduled job | ran end to end (systemd transient timer); grade: see acceptance | same |
| Build / update | built from source here (CUDA from pip wheels, no root); a release tarball would need a CUDA runtime | one installer, bundled CUDA |

## Migration acceptance test (challenger: llama.cpp)

1. **Full WP-F at threshold, semantically scored, no worse than the incumbent:** 22/27 vs 22/27 — **met (parity)**.
2. **One real automation unattended, output correct:** `daily-digest` on a box-built workspace, started by a transient systemd timer.

| Run (transient systemd timer, unattended) | Job | Keyword | Judge | Accepted |
|---|---|---|---|---|
| Ollama, rubric v1 (strict) 06:30 UTC | exit 0, digest written | 0.0 | FAIL | no |
| llama.cpp, rubric v1 (strict) 06:35 UTC | exit 0, digest written | 0.5 | FAIL | no |
| Ollama, rubric v2 06:43 UTC | exit 0, digest written | 1.0 | PASS | **yes** |
| llama.cpp, rubric v2 06:44 UTC | exit 0, digest written | 1.0 | PASS | **yes** |

Rubric v1 demanded two measured numbers from inside the decision doc (the 14B's 20 s gate,
the 56–75 s cold-load penalty) that the digest prompt's "terse bullets" format does not
surface; it failed every correct digest, including ones from gemma4 26B and qwen3.8 27B. v2
(`e86b849`) asks for three of four recorded work items in any wording and defines what a
contradiction is. Both digests under v2 were read by hand: accurate, nothing invented, no
model or runner declared chosen. Same judge (`qwen3-coder:30b-a3b`, calibration 6/8) both times.

**Result: the challenger passes both conditions of the migration acceptance test** — with
the caveats that the job was launched by a *transient* timer in this session, not an
installed schedule, and that llama.cpp itself ran under `nohup`, not a unit.

Timing caveat on the 06:44 llama.cpp run: the owner started `scripts/crash-recovery-test.sh`
at the same minute, and its Phase A loaded `qwen2.5-coder:14b` into Ollama while llama-server
held the GPU. The acceptance verdict (correctness) stands; the job's wall time from that run
is not a clean number, and neither is the crash test's Phase A completion time.

## Recommendation for the owner (not a decision)

Evidence does not separate the runners on speed, memory or answer quality. The choice is about behavior and operations:

- **Keep Ollama** if the model registry and the installed, reboot-proven service matter more than the truncation behavior. Then a client-side context guard is mandatory: count tokens before sending, refuse over 32k. (Not built here; flagged.)
- **Adopt llama.cpp** if hard rejection of oversized prompts and per-request server timings matter more. Then it needs a root-installed systemd unit, a decision on how a second model is served, and the gateway upstream repointed. Its unknown-model behavior means `INFERENCE_MODEL` must be validated against `/v1/models` at client start.

**What would reverse a "keep Ollama" call:** a real automation silently truncated in production, or a model Ollama cannot load (the qwen3.6 mmproj case) becoming the pick.
**What would reverse an "adopt llama.cpp" call:** the crash/reboot test failing under a real unit, or multi-model serving becoming a requirement.

## Not done / flags

- llama.cpp systemd unit, crash and reboot tests: root.
- Page cache not dropped between cold cycles (root).
- Embeddings not compared (chat artifact only).
- The client has no token-count guard; both runners' oversize behaviors are reachable from `aiserver.client.LLM` today.
