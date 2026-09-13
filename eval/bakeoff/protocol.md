# WP-H bakeoff protocol — Ollama vs llama.cpp

**Frozen:** 2026-09-13, before the first bakeoff measurement. If anything below changes, the
earlier numbers are void. Re-freeze the protocol with a new date and measure both runners again.

**Scope:** which program serves the endpoint. This does not pick a model. The artifact below
is the one the evidence currently leads with, and it was chosen *because* it is fixed. It is
not a recommendation. Declaring a winner permanent is the owner's call
(`NORTHSTAR.md`).

## Identity — held identical across both runners

| Item | Value |
|---|---|
| Hardware profile | `mybuddy-3090-02`: i9-14900KF, RTX 3090 24 GB, driver 595.91.07, Ubuntu 26.04.1, model store `/srv/models` (ADATA SX8200PNP, ext4 noatime) |
| Model artifact | **one file:** `/srv/models/blobs/sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a` (18,556,688,736 B, GGUF, `qwen3moe`, file_type 15 = Q4_K_M). Ollama serves it as `qwen3-coder:30b-a3b-q4_K_M`; llama-server loads the same path with `-m` and publishes the same name with `--alias`. |
| Quantization | Q4_K_M (it is the same file) |
| Context | 32768 tokens, one slot (Ollama `OLLAMA_NUM_PARALLEL=1` / llama-server `-np 1`) |
| KV cache | f16/f16 (Ollama `OLLAMA_KV_CACHE_TYPE` unset / llama-server `-ctk f16 -ctv f16`) |
| Flash attention | on (Ollama `OLLAMA_FLASH_ATTENTION=1` / llama-server `-fa on`) |
| GPU offload | all layers; the runner's own log must show 49/49 on GPU, or the run is void |
| Weights loading | mmap on both (the default for each) |
| Sampling | every request sends `temperature: 0`. Ollama applies this model's published params (`top_k 20`, `top_p 0.8`, `repeat_penalty 1.05`), so llama-server is started with the same three values. At temperature 0 only `repeat_penalty` can change output. |
| Chat template | **cannot be held identical, recorded as a known difference:** Ollama renders `qwen3moe` with its built-in Go renderer; llama-server uses the GGUF's embedded Jinja template (`--jinja`). Differences show up as output or tool-call differences and are reported, not normalized away. |
| Binaries | Ollama 0.34.0 (`/usr/local/bin/ollama`, its bundled CUDA 13 backend) · llama.cpp `b10937` (commit `56b9eb2`), built on the box with `GGML_CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=86`, CUDA 13.2.86 toolchain from NVIDIA's pip wheels (no system CUDA toolkit; no root) |
| Grader | WP-F at box-mission commit of this protocol: `eval/cases.jsonl` (27 cases), `eval/scoring.py`, judge `eval/judge.py` with the calibration set. The judge model is the artifact itself, served by the runner under test (the two 18.5 GB runners cannot share the card). |
| Network | Ollama on its existing systemd bind (firewalled to LAN/tailnet, see `WP-E`); llama-server bound to **127.0.0.1 only**. Nothing is bound publicly, including during the bakeoff. |

## Corpus

- **Timing corpus:** the three deterministic long documents in `eval/longinputs.py`, each wrapped
  in its WP-F long case prompt: `ops_log` (~27.0k tokens), `worker_log` (~26.0k),
  `docs_corpus` (~20.8k), counted by this artifact's tokenizer. The token counts each runner
  reports are recorded; tokenization parity is a result, not an assumption.
- **Prefix-cache control:** every timed request starts with a unique first line
  (`[bakeoff <doc> rep <n>]`). No two timed requests share a prefix, so TTFT measures prefill
  and not a prompt-cache hit. The text is identical across runners.
- **Decode corpus:** one fixed prompt that asks for a long enumeration, `max_tokens: 512`.
- **Semantic corpus:** the full WP-F case set.
- Synthetic, no client data (OCR hard stop 2026-08-24).

## State definitions

- **Only one runner holds the GPU at a time.** Before measuring llama-server, Ollama has no
  model loaded (`/api/ps` empty, verified). Before measuring Ollama, llama-server is stopped.
  Between runners, GPU memory must read < 600 MiB.
- **Cold (process-cold):**
  - *llama-server:* the process is started with the model path. `ready_s` is the time from
    `exec` until `GET /v1/models` returns 200. Then the first request's TTFT is measured.
  - *Ollama:* the server is running and no model is loaded (unloaded via the runner API).
    `ready_s` = 0 and the first request's TTFT includes the model load.
  - *Compared value:* `ready_s + ttft_s`.
  - *Repetitions:* 3 cycles per runner.
- **Page cache is not dropped** (no root in this session). Question (b) measured disk-cold ≈
  process-cold on this drive (within ±10 %), so this is recorded, not corrected for.
- **Warm:** the model is resident after one untimed warm-up request. Then 5 timed requests per
  long document, plus 3 decode requests.

## What is emitted

- **Raw data:** `out/bakeoff/<runner>-<phase>-<UTC>.jsonl`, one record per request: prompt and
  completion tokens, `ttft_s`, `ttfc_s`, `total_s`, derived prefill tok/s (`prompt_tokens / ttft_s`)
  and decode tok/s (`(completion_tokens − 1) / (total_s − ttft_s)`), peak GPU memory during the
  request (nvidia-smi at 250 ms), finish reason, error, and any server timing object verbatim.
- **Probes** (same file set): real `tool_calls` array vs a tool call written as prose;
  `response_format: json_schema` with `additionalProperties: false` and an enum (does it
  constrain or advise); streaming shape (chunks, finish reason, usage); unknown-model error
  shape; oversize prompt (2× `ops_log`, ~54k tokens): rejected, or silently truncated;
  `/v1/models` lists the served name. Embeddings are **not measured** (a chat artifact; the
  embedding model is a separate instance).
- **Report:** `out/bakeoff/report-YYYY-MM-DD.md` with both runners side by side: p50 / p90 / max, not means.

## Operational checks

- **Restart reliability:** SIGKILL → does the endpoint serve again unattended?
  - *Ollama:* systemd `Restart=always` (WP-E `scripts/crash-recovery-test.sh`, needs root).
  - *llama-server:* it has no unit in this session. It is run under a supervising loop, which is
    **recorded as "not equivalent to systemd"** until a root-installed unit exists.
- **Reboot behavior, remote client over Tailscale through the gateway, unattended scheduled job:**
  these need root, the gateway pointed at the challenger, or a reboot, and are recorded as not
  run where this session cannot run them.

## Migration acceptance (challenger only)

A runner is adopted only when, against it:

1. the full WP-F set passes at `EVAL_PASS_THRESHOLD` (0.8) per case, semantically scored, with
   a pass rate no worse than the incumbent's on the same artifact; **and**
2. one real automation runs unattended on its own schedule, start to finish, and its output is
   graded correct.

Both results are recorded whether the challenger passes or not.
