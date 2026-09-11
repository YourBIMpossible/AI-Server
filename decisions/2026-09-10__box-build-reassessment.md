# Box-build reassessment — three months on

**Date:** 2026-09-10
**Trigger:** the 3090 box powered on for the first time; OS install imminent.
**Reassesses:** `PROGRAM_PLAN.md` and `AI-Brain-Data/_status/AI-Server_Build_and_Integration_Plan.md`, both stamped 2026-06-16.
**Status:** analysis + recommendation. The mission question it raises is drafted at `NORTHSTAR.draft.md` for the owner to lock.

---

## TL;DR

Build the box. The case for it is **stronger** than it was in June — but for reasons that
did not exist in June, and the *customer-facing* reason that justified it in June is gone.
Three of the four things measured to be broken on the 5080 are caused by it being a
shared Windows desktop, and a headless Linux box fixes them directly.

Two things in this repo are actively wrong and would bite on install night: the
"relocation is one `.env` line" claim, and `scripts/setup-linux.sh` shipping without the
serving-layer environment that is worth up to 150× on prefill.

---

## The four inputs

### 1. `F:\Local Intel` — the only place local inference has actually been measured

A separate falsification experiment ("does local model triage of test logs add value
*beyond deterministic log compression alone*") that neither project knows the other
exists. It is not a competitor to AI-Server; it is the only empirical evidence we have
about the substrate, and the numbers are decisive.

Measured on the 5080 rig (Ollama 0.32.14, 15.9 GB VRAM):

| Finding | Number | Source |
|---|---|---|
| Flash attention off → on, prefill | **1.9 → 288 tok/s** (~150×) | `WORKLOG.md:252-270` |
| Same, large-prompt main instance | **1.9 → 6,335 tok/s** | `WORKLOG.md:99-101` |
| `qwen3-coder:30b-a3b` residency @32k | **66.16 %** — 21 layers overflow | `hardware_profiles/workstation-zeria-01.json:55-78` |
| Desktop apps holding VRAM | **~4.7 GB** | `PHASE0_OPERATIONAL_REPORT_2026-09-06.md:33` |
| Cold model load (mmap disabled on Win+CUDA) | **56–75 s**; worst request 58.0 s | `PHASE0_REPORT_FA-ON_2026-09-06.md:83-91` |
| `qwen2.5-coder:14b` warm, median | **19.2 s — 2 of 4 runs over the 20 s gate** | `PHASE0_OPERATIONAL_REPORT_2026-09-06.md:54,102` |
| `qwen3.5:9b` prefill vs the coders | **5,267 vs ~2,100 tok/s**, 8.3 GB peak | `PHASE0_OPERATIONAL_REPORT_2026-09-06.md:47-58` |

Locked by human ruling 2026-09-06 (`decisions/2026-09-06-defer-revision-warm-session-only.md`):
local models approved **for warm sessions only**; cold start explicitly not guaranteed.
30B-A3B eligible, 14B **not admitted**, 9B unresolved.

Quality was never the bottleneck but is not proven either: structure 5/5 and citations
10/10, yet **classification accuracy only 8/10**, and the model tagged a definite
root-cause statement as `unlikely`.

### 2. `F:\AI-Models Local` — empty; the real store is elsewhere

That folder holds no models at all. The library is at `C:\Users\Zeria\.ollama\models`,
**32.05 GB across 19 blobs**: `qwen3-coder:30b-a3b-q4_K_M` (17.28 GB, shared blob with
`qwen3-coder-32k`), `qwen2.5-coder:14b` (8.37 GB), `qwen3.5:9b` (6.14 GB, pulled
2026-09-05, untriaged and not wired into anything), `nomic-embed-text` (0.26 GB).

opencode points both `model` and `small_model` at `ollama/qwen3-coder-32k` — the 14B is
explicitly flagged `"tool_call": false`. The plan's "14B workhorse" role has already been
demoted in practice.

### 3. `F:\AI-Brain-Data` — frozen

`decision-log/` stops at 2026-05-28, three weeks *before* the build plan. `journal/` is
empty. One commit since June, and it is automated pipeline data. **The vault's build plan
is a stale twin of `PROGRAM_PLAN.md`** — two docs that cross-reference each other as
companions, where only one has moved. Fold it into the repo and leave a pointer.

### 4. `F:\BIMpossible-Workspace` — the demand side changed shape

This is the finding that most changes the plan.

- **2026-07-27 (PLACED, not ratified):** owner judged local models *"will not land with
  real clients or their hardware."* Slice 14d (`LocalOllamaProvider`) is
  deferred-with-trigger, gated on a named air-gapped customer, and **is no longer the
  mechanism for security levels** — that moved to cloud-side data-handling policy flags.
- **Neither shipped retrieval path uses embeddings.** Phase 15b (live 2026-08-31) and the
  CKA spec both chose **BM25**. WP-B's sqlite-vec store currently has **no BIMpossible
  consumer**.
- **The largest new local demand is internal, and unratified:** Phase 19 "BIMpossible
  Workbench" (`2026-08-21`, PROPOSAL) names the Ollama HTTP API as its stack for
  normalizing notes, summarizing logs, categorizing files, extracting relations.
- **GPU OCR is real demand but hard-stopped:** ~9 GB VRAM, torch cu129 — paused
  2026-08-24 on a csuite HARD STOP over client-data exposure.
- The one durable contract is **OpenAI-compatible endpoint + configurable `base_url`**,
  which this repo already commits to.

### 5. Public landscape — moved twice, and the lesson is not "re-pin"

> **Source-quality caveat, carried forward deliberately.** Search for current local models
> returns mostly AI-generated SEO content that contradicts itself on names and version
> numbers. The engine/config findings below are sourced to GitHub issues and official
> docs and I trust them. **The specific model names are NOT verified** — treat them as
> candidates to check at pull time, never as picks to hard-code.

Trustworthy (official docs / tracked issues):

- **Ollama is at 0.34.0** (2026-09-05); the rig runs 0.32.14. 0.32.15 roughly halved TTFT
  by caching resolved model metadata.
- **`OLLAMA_CONTEXT_LENGTH` still defaults to 4096.** A 27k-token prompt against a default
  install is silently truncated. This alone invalidates any first benchmark on the box.
- **`OLLAMA_KV_CACHE_TYPE` still defaults to `f16`.** The "q8_0 is nearly free" claim is
  repeated everywhere with **no rigorous public measurement**, and none for
  citation-grounded extraction. Quantized KV requires FA and *silently falls back* to f16
  on unsupported architectures (ollama#13337).
- **Flash attention is now automatic when the backend supports it**, with the env var as a
  three-state override. Set it explicitly regardless.
- **Qwen3.6 GGUF + mmproj still does not load in Ollama** (ollama#14730, #15898, both
  open). Text-only works.
- **vLLM: drop it from the plan.** FP8 needs Hopper/Ada/Blackwell — the 3090 is Ampere and
  gets nothing. vLLM's 2026 direction is entirely enterprise multi-GPU. It buys
  concurrency this box does not need and costs VRAM it cannot spare.
- **Ubuntu 26.04 LTS** is current. NVIDIA Container Toolkit ≥1.18 generates a CDI spec
  just-in-time and needs Docker ≥26; re-run `nvidia-ctk runtime configure` after every
  driver update.
- **Budget ~20 GB, not 16**, for a 27–30B Q4 at 32k with f16 KV.

---

## Verdict on the box

**Build it.** The June justification (serve on-device RAG to BIMpossible customers) is
gone, but a better-evidenced one replaced it. Every headline failure measured on the 5080
is a *shared-desktop* failure, not a model failure:

| Measured problem | What the box does to it |
|---|---|
| 4.7 GB VRAM held by desktop apps → 30B-A3B at 66 % residency | Headless: the GPU is the inference GPU. 24 GB should hold 30B-A3B fully at 32k |
| mmap disabled on Windows+CUDA → 56–75 s cold loads | Linux restores mmap — the most likely single cure |
| Warm-session-only policy needs the model resident | An always-on box can honour `keep_alive`; a rig used for gaming and Revit cannot |
| Every benchmark void when hardware changes | A dedicated box makes the hardware profile *stable* — which is what Local Intel's protocol requires to make progress at all |

The box is not "more VRAM for bigger models." It is **the thing that makes local inference
measurable and therefore decidable.** That is a better reason than the one it had in June.

## What is wrong in this repo right now

1. **`.env.example:8` and `relocate.md` claim `OLLAMA_HOST` is "the only line that changes
   on relocation." This is false.** The 150× lives in server-process environment that this
   repo does not contain — `grep -rE 'FLASH_ATTENTION|KV_CACHE|KEEP_ALIVE|NUM_PARALLEL'`
   over the tree returned zero hits before today. The portability contract must cover the
   serving layer, not just the host URL.
2. **`scripts/setup-linux.sh` would have produced a slow box.** It set `OLLAMA_HOST` and
   nothing else — no FA, no keep-alive, 4096 context. *(Fixed in this commit.)*
3. **`config/models.txt` recommends `qwen2.5-coder:32b` / `llama3.3:70b`** for the box.
   Both predate every measurement above, and 14B is already known tool-call-incapable.
4. **The vault build plan duplicates `PROGRAM_PLAN.md`** and has not moved since June.
5. **WP-B's vector store has no consumer.** Worth saying out loud before more is built on
   it.

## Recommended path

**Tonight — OS and a correct baseline.** Ubuntu Server 26.04 LTS headless. BIOS first:
microcode 0x12B+ and the Intel Default power profile, both non-negotiable for an always-on
14900K. Then driver, then `scripts/setup-linux.sh` (now writes the full serving-layer
env), then **verify from the Ollama startup banner, never the shell** — a stale-env trap
already cost a full measurement batch on the rig.

**First week — re-measure, do not port.** Every number in this doc is void on new
hardware; Local Intel's own protocol makes the hardware profile part of batch identity.
Re-run phase 0 on the box. The specific questions worth answering: does 30B-A3B go fully
resident at 32k, does Linux mmap kill the cold-load penalty, and does 14B clear the 20 s
gate once 4.7 GB of desktop contention is gone.

**Then — let the evidence pick the models.** Do not hard-code new names into
`config/models.txt`; that is exactly how the June picks went stale in twelve weeks. The
repo is already config-driven — the missing piece is a scored comparison, which is WP-F,
which is already specified. Pull two or three current candidates at build time, verify
them against the library rather than against a blog, and let WP-F rank them. Note that
**WP-F must score semantics, not just schema** — structural validity passed everywhere on
the rig while classification sat at 8/10.

**Deliberately not doing:** vLLM (Ampere gets nothing from it), a bigger embedding model
(no consumer yet), and 14d `LocalOllamaProvider` (owner-deferred, demand-gated).

## Open calls

1. **What the box is for.** Drafted at `NORTHSTAR.draft.md` — rename to drop `.draft` to
   lock it. The honest framing is "internal inference substrate + the instrument that
   makes Local Intel decidable," not "product infrastructure."
2. **Does Local Intel's phase-1a admission move to the box?** It is blocked on a call the
   owner owes, and the box changes the substrate underneath it. Cheapest path is to admit
   on box-measured numbers rather than re-litigating the rig's.
3. **Fold the vault build plan into `PROGRAM_PLAN.md`?** Recommended: yes, pointer left
   behind.
4. **Phase 19 Workbench** is the largest named consumer and is unratified. If it is not
   going to be ratified, the box's internal-demand case rests on AI-Server's own
   automations plus opencode — still sufficient, but worth knowing.

## Verified, not assumed

`F:\AI-Dev` was purged from *this repo's config and docs* on 2026-09-07 but **still exists
on disk** — the opencode launchers under `F:\AI-Dev\.tools\opencode\` still resolve. An
earlier reading that the directory was deleted is wrong.

---

# Addendum — 2026-09-11: the runner is not the mission

**Origin:** owner critique, same day. Verbatim premise: *"Ollama is not the only option, and
it should not become an unexamined platform dependency."*

## What was wrong with the doc above

The critique is correct and it lands on this document. The reassessment carried real evidence
about the *serving layer* — flash attention, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_KEEP_ALIVE`,
`OLLAMA_KV_CACHE_TYPE` — and those findings are sound. But Ollama was the carrier for all of
them, so a page of wins for **configuration** read as a page of wins for **Ollama**. Nothing
above ever argued that Ollama should be the serving standard. It just never argued that it
shouldn't, and inevitability grew in the gap.

That was already ossifying in code: `.env.example` named the client's endpoint setting
`OLLAMA_HOST`, so every consumer inherited a runner name for what is merely an HTTP contract.
Worse, it was a live footgun — `config.py` reads process env for any key it knows, and
`OLLAMA_HOST=0.0.0.0:11434` is exactly what Ollama's own docs tell you to export **on the
box**. A shell that had it set would have silently repointed every client at a bind address.

## The decision

**What is being built is a private, headless, OpenAI-compatible inference endpoint.** Ollama
is the initial baseline runner. Runner selection remains an evidence-backed decision.

Adopted verdicts:

| Claim | Verdict |
|---|---|
| Dedicated headless Linux box | Strong case — unchanged from above |
| Private OpenAI-compatible endpoint | Strong case |
| Ollama as *initial baseline* | Reasonable |
| Ollama as *permanent serving standard* | **Unproven. Uncommitted.** |
| vLLM on a single-user 3090 | Not justified — no FP8 on Ampere, nothing for batching to do |
| llama.cpp as contender | Worth evaluating, once the box is operational |

## What changed in the repo (2026-09-11)

Client configuration is now decoupled from Ollama configuration:

- `OLLAMA_HOST` → `INFERENCE_BASE_URL` (carries `/v1`; a bare host:port is normalized, an
  explicit path is respected). `OLLAMA_API_KEY` → `INFERENCE_API_KEY`. `MODEL` /
  `EMBED_MODEL` → `INFERENCE_MODEL` / `INFERENCE_EMBED_MODEL`, documented to prefer a
  **server-side alias** (`local-workhorse`) over a runner-specific pull tag.
- `config.py` **raises** on any stale key rather than silently falling back to a default —
  except when the new name is also present, since `OLLAMA_HOST` remains legitimate on the box
  as a *server bind address*. Two meanings, one name, now unambiguous.
- `client.py` was already clean (`/v1/*`, no CLI shellouts); `ping()` moved from Ollama's
  `/api/tags` to the portable `/v1/models`. No adapter layer was needed — worth stating, since
  the cost of neutrality here turned out to be naming, not architecture.
- `aiserver_status.py`: liveness and the model list come from `/v1/models`; `/api/ps` (loaded
  models + VRAM, no OpenAI equivalent) is demoted to best-effort enrichment behind a
  `models_loaded_supported` flag. Runner-native detail is *declared missing*, never a failure.
- `docker-compose.yml` healthcheck now asserts `/v1/models`, and gained the serving-layer env
  the compose path was missing (the same defect found in `setup-linux.sh`).
- New: `handoffs/WP-H_runner-bakeoff.md` — the bounded Ollama-vs-llama.cpp test.

## The gate

**Portability is a gate, not a promise.** `/v1/models` answering is not acceptance. "OpenAI-
compatible" says nothing about chat-template behavior, tool-call serialization, JSON-schema
constrained generation, streaming semantics, embedding endpoints, tokenization and context
accounting, model aliasing, or error and retry behavior — each can differ silently while
everything appears to work.

A runner is adopted only when the **full WP-F workload passes semantically against it** *and*
**a real automation completes unattended on its own schedule**. Until then, no runner is
permanent — including the one currently installed.
