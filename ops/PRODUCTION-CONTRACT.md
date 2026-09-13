# Production model / runtime contract

**Box:** `mybuddy` (i9-14900K · RTX 3090 24 GB) · **Since:** 2026-09-13 · **Owner:** operator.
Change this file only alongside the decision note that justifies the change.

## The endpoint

- **Contract:** one private, OpenAI-compatible HTTP endpoint. Clients use only
  `INFERENCE_BASE_URL`, `INFERENCE_API_KEY`, `INFERENCE_MODEL` (`.env`, read via
  `aiserver.load_config`). No runner name in application code, config keys or automations.
- **Served runner today:** Ollama, chosen as a deployment decision after the WP-H tie
  (`decisions/2026-09-13__runner-and-model-pick.md`). Not permanent (`NORTHSTAR.md`).
- **Endpoint:** LAN/Tailscale only. Direct `:11434`, key-gated gateway on `:11440`
  (`ops/Caddyfile`, `ops/systemd/aiserver-gateway.service`). Never port-forwarded.

## Models

| Role | Tag | Notes |
|---|---|---|
| Production (always resident) | `gemma4:26b-a4b-it-q4_K_M` | WP-F 27/27; fastest on long-context cases; fully GPU-resident at 32k with f16 KV. Canonical list: `config/models.txt`. |
| On-demand coding | `qwen3-coder:30b` | Loaded only when asked for by name; evicts the production model while resident. |
| Embeddings | `INFERENCE_EMBED_MODEL` in `.env` | Small; coexists. |

**One large model at a time.** 24 GB cannot hold both large models with their KV caches.
Requesting the coding model unloads the production model; the next production request pays a
cold load. This is expected, not a fault — but it means an *interactive* coding session and an
*unattended* automation should not overlap. Automations are scheduled off-hours for that reason.

## Context policy

The served context window and the client-side guard are configuration, not this document.
Canonical values live in:

- **Server side:** the runner's unit/environment set up by `scripts/setup-linux.sh` /
  `scripts/setup-ops.sh` (Ollama env), and `scripts/bakeoff-runner.sh` for the llama.cpp
  reference flags (`-c`, `-ctk/-ctv`, `-np`, `-fa`).
- **Client side:** `INFERENCE_MAX_INPUT_TOKENS` (`aiserver/config.py` `_DEFAULTS`), enforced by
  `aiserver.client.LLM` which refuses an over-budget prompt with `PromptTooLargeError`.

Keep the two in agreement. If the server window changes, change the `.env` guard in the same
change, and treat it as a benchmark trigger (`decisions/2026-09-13__benchmark-policy.md` §3).

## Known caveats (measured, WP-H)

- **Ollama silently truncates** a prompt over its context window to roughly half and answers
  HTTP 200. The client-side guard above is the only protection; do not disable it (`0`) in
  production `.env`.
- **llama.cpp answers any model name** with whatever model it has loaded (no 404). A typo in
  `INFERENCE_MODEL` is invisible under llama.cpp. If llama.cpp is ever served, `INFERENCE_MODEL`
  must match `--alias` and the smoke test must assert the returned `model` field.
- A **runner switch disrupts the endpoint**: the port, the unit and the model registry change.
  Every client sees the outage. It is never done implicitly.

## Exclusive GPU work

Runner swaps, full bakeoffs, GPU-monopolising eval runs and long-context stress probes take the
interlock in `aiserver/gpulock.py` (default path `/etc/ai-server/bakeoff.lock`, overridable via
`GPU_LOCK_PATH`; Personal-OCR reads the same file through `WP_H_BAKEOFF_LOCK`). Ordinary
inference and read-only analysis (automations, RAG, scout) never take it. Stale locks are
reported, never auto-cleared; `scripts/gpu_lock.py clear` is an operator action and kills nothing.

One-time setup on the box (the default directory is root-owned):

```bash
sudo install -d -m 0775 -o "$USER" -g "$USER" /etc/ai-server
```

## Preflight — deliberate runner swap

Run through in order; stop at the first "no".

1. **Trigger named.** Which item of the benchmark policy applies? Write it down first.
2. **Nothing scheduled.** `systemctl --user list-timers` (and Windows Task Scheduler on the rig)
   shows no automation due during the window; no interactive session is using the endpoint.
3. **Lock taken.** `scripts/gpu_lock.py run --purpose "runner swap: <why>" -- <command>` or an
   explicit `acquire` for a manual session. `scripts/gpu_lock.py status` shows you as owner.
4. **GPU empty.** `scripts/bakeoff-runner.sh ollama-unload` reports no models loaded.
5. **Same artifact.** The replacement serves the *same GGUF blob* and quant as production, with
   context / KV dtype / parallelism matching the canonical values above.
6. **Client guard aligned.** `INFERENCE_MAX_INPUT_TOKENS` equals the new server window.
7. **Acceptance, not `/v1/models`.** `scripts/smoke-test.py`, then the full WP-F set and one
   unattended real automation pass against the replacement — under the managed venv interpreter
   (`decisions/2026-09-13__scheduled-acceptance-env-gap.md`).
8. **Decision note written**, `.env` on every client updated in the same change, lock released
   (`status` shows free), endpoint watch (`ops/systemd/aiserver-endpoint-watch.timer`) green.

Rollback is the same list in reverse; the lock is held until the original runner answers the
smoke test again.
