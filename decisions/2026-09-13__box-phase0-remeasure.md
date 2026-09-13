# Phase 0 re-measured on the box — and the 24GB candidates

**Date:** 2026-09-13
**Box:** `mybuddy` — i9-14900KF / RTX 3090 24GB / driver 595.91.07 / Ubuntu 26.04.1 / Ollama 0.34.0
**Answers:** the three open Phase 0 questions in `NORTHSTAR.md`, plus the model-candidate and WP-E autostart steps.
**Status:** evidence only. No model is picked, `config/models.txt` is untouched, no runner is declared permanent.

---

## TL;DR

- **(a) 30B-A3B at 32k: fully resident.** 49/49 layers on GPU, 0 overflowing, peak 21,064 MiB of 24,576. (Rig: 66%.)
- **(c) 14B still misses the 20 s gate** with zero desktop contention: genuine warm median **20,852 ms, 2 of 4 over**. The harness's 19,991 ms median includes a prompt-cache hit. The cause is prefill throughput (~1,687 tok/s on the 3090), not VRAM.
- **(b) cold load: the penalty is gone.** Disk-cold from the ADATA: 14B **4.8 s**, 30B-A3B **8.4 s** (rig: 56–75 s). Disk-cold ≈ process-cold, so reading weights off disk is no longer a meaningful cost.
- **Candidates:** none of the four new ones beats `qwen3-coder:30b-a3b` (10/10 valid, 8/10 classification). Classification: gemma4 31B 4/10, the other three 0/10. gemma4 31B and nemotron do not fit fully at 32k. **WP-F's 17 cases cannot rank models** (every model scores 17/17).
- **WP-E autostart: passes.** Ollama came up after `/srv/models` mounted, with all serving settings intact. Security flag: it listens on `0.0.0.0`.

---

## How this was measured

**Instrument:** the existing Phase 0 harness, `github.com/YourBIMpossible/local-intel`
(`run_phase0_operational.py`) — not a new one. It was Windows-only in two places; the Linux
adaptations are additive and dated, on local branch `box-mybuddy-linux` (not pushed):

| Commit | Change |
|---|---|
| `ebe0dcf` | Server banner + per-load log segments read from journald (was `AppData\…\server.log`); Linux branch of `detect_hardware_profile`; `REQUEST_KEEP_ALIVE` 10m → 30m, implementing ruling item 2 of `decisions/2026-09-06-defer-revision-warm-session-only.md`; server keep-alive start check accepts any duration ≥ 30m (this box runs `-1`) |
| `34c35dc` | Batch evidence, profile `mybuddy-3090-01` |
| `5e73956` | Profile `mybuddy-3090-02` (model store moved) |

No threshold, fixture, generation parameter, gate or stop condition changed. local-intel tests:
93 pass; two sampler-timing tests fail identically on untouched `master` on this host.

**Every condition started from an empty GPU.** `qwen2.5-coder:14b` was resident (server
`OLLAMA_KEEP_ALIVE=-1`, `MAX_LOADED_MODELS=2`, 14.9 GB). It was unloaded and `/api/ps` proven
empty before profile capture, before the batch, and before every candidate probe; each
condition's `ps_before` is in the results JSON. Without this, a 30B-class model would have been
measured as spilling when it does not.

**Serving layer, from the service's own journald banner:** `OLLAMA_FLASH_ATTENTION:true`,
`OLLAMA_CONTEXT_LENGTH:32768`, `OLLAMA_KV_CACHE_TYPE:` (f16), keep-alive -1. Every load segment
logged `flash_attn = enabled`, KV f16/f16, `n_ctx 32768`.

### Two hardware profiles — never mix them

| Profile | Model store | Device | Valid for |
|---|---|---|---|
| `mybuddy-3090-01` (hash `23e37231…`) | `/usr/share/ollama/.ollama/models` on the root LV | Sabrent 512GB NVMe (root LV) | (a), (c), candidate residency, WP-F — GPU-bound |
| `mybuddy-3090-02` (hash `de36125d…`) | `/srv/models` (dedicated, ext4 noatime) | ADATA SX8200PNP 1TB, fstab UUID `cde2139a…` | (b) and every drive-bound number |

Kernel `nvmeN` names swap between boots (the ADATA was `nvme0n1` in this session, then `nvme1n1` after the reboot), so drives are named by model and UUID here. Mid-session the owner mounted two dedicated 1TB drives. The model store moved to `/srv/models`
(systemd drop-in `models-store.conf`: `OLLAMA_MODELS=/srv/models` + `RequiresMountsFor=/srv/models`),
verified from the startup banner (`OLLAMA_MODELS:/srv/models`). Because the drive is part of batch
identity, cold-load numbers taken on `-01` are **not** used for (b).

---

## (a) Does 30B-A3B go fully GPU-resident at 32k? — **Yes**

Profile `-01`, batch `2026-09-13T012129Z`.

| | Rig (5080, Windows) | Box (3090, Linux) |
|---|---|---|
| Layers offloaded | 49/49, **21 overflowing** | **49/49, 0 overflowing** |
| Residency | 66.16 % | **100 %** (`size_vram == size`, 21,718,567,484 B) |
| Peak VRAM, warm | 14,977 MiB (capped by desktop) | 21,064 MiB |

## (c) Does 14B clear its 20 s gate without desktop contention? — **No**

Profile `-01`, same batch. Fixtures are the frozen five (~27.3k prompt tokens).

| Warm run | f01 | f02 | f03 | f04 | f05 |
|---|---|---|---|---|---|
| Total ms | 2,619 *(prompt-cache hit — excluded)* | 21,712 | 22,160 | 19,991 | 18,250 |
| Prefill tok/s | — | 1,633 | 1,661 | 1,687 | 1,756 |

- Harness 5-run warm median: 19,991 ms (reported "PASS"). **Genuine 4-run median: 20,852 ms; 2 of 4 over.**
- Same pattern as the rig (19,157 ms genuine median, 2 of 4 over). Removing 4.7 GB of desktop VRAM
  contention fixed residency (49/49 now vs 47/49) but **not** latency.
- Prefill is ~16 s of every ~20 s request. The 3090 prefills this model *slower* than the 5080
  did (1,687 vs 2,143 tok/s). Cold median total 20,750 ms, load 1,939 ms.
- Structural validity 10/10, citations 10/10, **classification 8/10** (misses f01 both states).

For contrast, same batch: **30B-A3B** genuine warm median **13,495 ms** (0 over), prefill
~2,600 tok/s, decode ~110 tok/s, validity 10/10, citations 10/10, classification 8/10 (misses f02
both states). **`qwen3.5:9b` control:** prefill ~3,760 tok/s, but 0/10 structurally valid — every
run `unparseable`, same as the rig; still an open output-handling question, not a model verdict.

## (b) Does Linux mmap eliminate the 56–75 s cold-load penalty? — **Yes**

Measured on `mybuddy-3090-02` only: pass 1 = first load of each model since reboot (disk-cold from
the ADATA), pass 2 = process-cold with warm page cache. Cold requests only; (a)/(c) not re-run.
Boot 02:16 UTC; the first request of the boot was pass 1's first load (journald shows no earlier
`GIN` line). Page cache was 1 GB at start. Every load logged `load_mode = mmap` and read blobs from
`/srv/models/blobs/`. Evidence: local-intel `phase0_results/coldload_b_mybuddy-3090-02_2026-09-13T021822Z.json`
(pass 1) and `…T022214Z.json` (pass 2). Fixture f01.

| Model | Disk-cold load (ms) | Process-cold load (ms) | Residency at 32k |
|---|---|---|---|
| qwen2.5-coder:14b | **4,799** | 5,099 | 49/49, 100 % |
| qwen3-coder:30b-a3b-q4_K_M | **8,382** | 8,529 | 49/49, 100 % |
| gemma4:26b-a4b-it-q4_K_M | 9,288 | 8,871 | 31/31, 100 % |
| qwen3.8:27b-q4_K_M | 8,733 | 8,267 | 66/66, 100 % |
| gemma4:31b-it-q4_K_M | 11,553 | 12,838 | 60/61, **92.5 %** |
| nemotron-3.5-lightning:30b-a3b-q4_K_M | ≈10,000 † | 14,198 | 54/54 with 5 partial (CPU tensor overrides), **85.7 %** |

- **The 56–75 s penalty is gone:** 4.8 s (14B) and 8.4 s (30B-A3B) from a cold disk, 7–12× faster than the rig.
- **Disk-cold ≈ process-cold** (within ±10 %, no consistent direction). Reading weights off the
  NVMe is no longer a real cost; what remains is GPU upload plus allocation. Warming the page
  cache is not worth doing.
- † The pass-1 nemotron result was lost: the driver's journald read crashed on a non-UTF-8 byte
  after the load finished. The value comes from the journal's own timestamps (`load_tensors`
  start 02:21:05.4 → `load_model: initializing` 02:21:15.3). Fix committed in local-intel
  `3b9ecf7` (`errors="replace"`, harness only); pass 2 ran on the fixed code.

Context carried from `-01` (Sabrent, process-cold, page cache uncontrolled — **not** the answer):
text-only models loaded in 1.9 s (14B) and 2.7 s (30B-A3B), `load_mode = mmap` in all 12 segments.
`qwen3.5:9b` logged `load_mode = none` on all 6 loads (vision projector present).

---

## 24GB model candidates

Checked against `ollama.com/library` tag pages on 2026-09-13, not a blog.

| Candidate | Tag | Size | Status |
|---|---|---|---|
| Qwen3-Coder 30B-A3B (MoE, 3B active) | `qwen3-coder:30b-a3b-q4_K_M` | 17.28 GiB | measured (batch above) |
| Gemma 4 26B-A4B (MoE, 4B active, vision) | `gemma4:26b-a4b-it-q4_K_M` | 16.75 GiB | measured (below) |
| Qwen3.8 27B (dense, vision) | `qwen3.8:27b-q4_K_M` | 16.52 GiB | measured (below) |
| Gemma 4 31B (dense, vision) | `gemma4:31b-it-q4_K_M` | 18.50 GiB | **does not fit at 32k** (92.5 % on GPU); measured (below) |
| Nemotron 3.5 Lightning 30B-A3B | `nemotron-3.5-lightning:30b-a3b-q4_K_M` | 23.68 GiB | **does not fit at 32k** (85.7 % on GPU); measured (below) |

### Phase 0 driver on the new candidates (`-02`, batch `2026-09-13T022541Z`)

The driver was run unmodified; only the model list changed. 5 fixtures × cold and warm = 10 runs per model.
The driver scores classification only on structurally valid output.

| Model | Valid | Classification | Warm median total | Warm prefill tok/s | Failure mode |
|---|---|---|---|---|---|
| *qwen3-coder:30b-a3b (ref, `-01`)* | *10/10* | *8/10* | *13,495 ms* | *~2,600* | — |
| gemma4:26b-a4b | 0/10 | 0/10 | 10,639 ms | 4,060 | 6× cites a `source_id` that is not in the packet (it cites the fixture ID); 4× truncated or unterminated JSON |
| gemma4:31b | 4/10 | **4/10** (f02, f05, both states) | 36,886 ms ✗ | 1,013 | 6× bad `source_id` citation; slow because it does not fit |
| qwen3.8:27b | 0/10 | 0/10 | 32,483 ms ✗ | 1,159 | 10× `unparseable`: response does not start with JSON (char 0) |
| nemotron-3.5-lightning | 0/10 | 0/10 | 17,686 ms | 1,903 | 10× `unparseable` at char 0 |

- Every run where the output was valid classified correctly. All the candidates' losses are
  **contract-following** failures: wrong citation IDs, or a non-JSON prefix.
- The char-0 `unparseable` result for qwen3.8 and nemotron is the same shape as `qwen3.5:9b`. The
  likely cause is a reasoning/thinking preamble. It is an **output-handling question, not a model
  verdict**. A fair re-test with thinking disabled or stripped is a harness change and was not
  made here.
- gemma4 26B-A4B is the fastest model measured (4k tok/s prefill). Its failures are semantic
  (citation IDs), not formatting, so it is the one worth a prompt-level look.

Excluded, with reason:
- **All `qwen3.6` tags** carry image input (no text-only tag exists) — the recorded mmproj load failure (ollama#14730, #15898).
- **`nemotron-3.5-lightning` nvfp4 / mxfp8** — FP4/FP8 formats; Ampere has no hardware support.
- **Cloud tags** — off-limits (fully local).

**Residency at 32k, from an empty GPU (`-01`):** all fully on GPU — 14B 100 %, 30B-A3B 100 %,
gemma4 26B-A4B 100 % (31/31 layers), qwen3.8 27B 100 % (66/66 layers). qwen3.8 loaded despite
its image projector, i.e. the qwen3.6 mmproj trap did not reproduce for it.

## WP-F scoring — the eval does not discriminate

`python -m eval.run` per model (`INFERENCE_MODEL` set in the process env; `.env` untouched), temperature 0:

| Model | Cases passed | Wall |
|---|---|---|
| qwen2.5-coder:14b | 17/17 | 3.3 s |
| qwen3-coder:30b-a3b-q4_K_M | 17/17 | 4.0 s |
| gemma4:26b-a4b-it-q4_K_M | 17/17 | 35.6 s |
| qwen3.8:27b-q4_K_M | 17/17 | 40.8 s |

Every model passes every case. **A harness every candidate aces cannot rank candidates.** The
cases are short, single-sentence prompts; the failure measured on real work (classification on
~27k-token logs, 8/10 for both measured models) never appears in them. Semantic ranking in this
document therefore uses the Phase 0 driver's `classification` vs `expected_classification`.
Flag (scope, not done here): WP-F needs harder, workload-sized cases before it can certify a model.

## WP-E autostart — **Passes**

Verified from this boot's journald (the owner rebooted, then nothing ran until the checks below):

- `02:16:37 Mounted srv-models.mount` → `02:16:40 Started ollama.service` with no manual step.
  Unit ordering is `After=srv-models.mount`, `RequiresMountsFor=/srv/models`.
- Startup banner: `OLLAMA_MODELS:/srv/models`, `OLLAMA_FLASH_ATTENTION:true`,
  `OLLAMA_CONTEXT_LENGTH:32768`, `OLLAMA_KEEP_ALIVE:2562047h47m16.854775807s` (= -1), 3090 found (CUDA, 23.6 GiB).
- **Security flag:** the banner also shows `OLLAMA_HOST:http://0.0.0.0:11434`, which listens on
  every interface. That is fine behind a NAT with no port forward, but it relies on the router,
  not the box. Bind to the LAN and Tailscale addresses, or add a host firewall rule, before WP-E is
  called done.

## Old model store

All loads this boot read blobs from `/srv/models/blobs/` (7 distinct blobs, zero references to
`/usr/share/ollama`). The 66 GB copy on the root LV is redundant. For the owner to run:

```
sudo rm -rf /usr/share/ollama/.ollama/models
```

## What is not answered here

- Which model to adopt — the owner's call, and WP-F as it stands cannot certify one.
- Runner choice — WP-H.
- Claude baseline — no `ANTHROPIC_API_KEY` on the box; recorded as skipped.

## Follow-ups (flagged, not done)

1. `scripts/setup-linux.sh` and `relocate.md` do not know about the dedicated model store; a fresh
   build would recreate the root-LV layout.
2. WP-F cases need workload-sized, semantically hard items (above).
3. local-intel branch `box-mybuddy-linux` is local only (now including `3b9ecf7`, the journald decode fix). Push when the owner approves.
4. `OLLAMA_HOST=0.0.0.0`: bind it to the LAN and Tailscale addresses, or firewall it (WP-E).
5. Thinking-model output handling (qwen3.8, nemotron, qwen3.5:9b) before those models can be scored.
6. The owner runs `sudo rm -rf /usr/share/ollama/.ollama/models` (66 GB, redundant, verified above).
