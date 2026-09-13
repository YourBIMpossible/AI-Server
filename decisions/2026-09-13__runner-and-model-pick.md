# Runner and model pick, and why --enforce stays off

**Date:** 2026-09-13 · **Box:** `mybuddy` · **Decides:** the two calls WP-H and WP-F left to the owner.

## Runner: keep Ollama as the served runner

WP-H (`decisions/2026-09-13__wp-h-runner-bakeoff.md`) found Ollama 0.34.0 and llama.cpp b10937
**tied on performance and correctness** on the same GGUF: warm TTFT 11.6s vs 11.55s on a 27k-token
prompt, prefill ~2,350 tok/s and decode ~190 tok/s on both, 22/27 on WP-F with 26/27 outputs
byte-identical. The evidence gives no performance or quality reason to move.

The deciders are operational, and they favour Ollama on this box: a systemd unit with
`Restart=always` that survived a real crash test and a reboot (WP-E), a model registry with
`MAX_LOADED_MODELS=2` on one port, and 404 on an unknown model name. llama.cpp has no unit
(root), serves one model per process addressed by blob path, and answers any model name with
whatever is loaded.

**This is a deployment choice, not a permanent verdict.** Per `NORTHSTAR.md`, no runner is
permanent; the contract is the OpenAI-compatible endpoint. No runner name appears in client code
or config keys -- clients still see only `INFERENCE_BASE_URL` / `INFERENCE_API_KEY` /
`INFERENCE_MODEL`. What reverses this: a production automation silently truncated past 32k with no
client-side guard (now mitigated -- see below), or a required model Ollama cannot load.

Ollama's one dangerous behaviour -- silently truncating a prompt over 32,768 tokens to ~16,386 and
returning HTTP 200 -- is now guarded client-side in `aiserver.client.LLM` (WP-H flagged it; commit
in this branch). That closes the gap that most argued for llama.cpp's hard HTTP 400.

## Model: gemma4:26b-a4b-it-q4_K_M

Written into `config/models.txt`. WP-F (`decisions/2026-09-13__wp-f-eval-separates-models.md`)
scored it 27/27, tied at the top with qwen3.8 27B and nemotron-3.5 30B-A3B but fastest on the
long-context cases (25.5s median vs 44.3s / 37.7s), and fully GPU-resident at 32k with f16 KV.
The two 27/27 rivals remain valid alternates; the eval saturates at the top and cannot rank them
further without harder cases.

## --enforce stays OFF

`scripts/setup-ops.sh --enforce` swaps the ufw rules so `:11434` is no longer reachable directly
and all traffic must go through the key-gated gateway on `:11440`. It stays **off**: this is a
private LAN/Tailscale box (`NORTHSTAR.md`: no public exposure), the gateway is verified working,
and flipping it breaks the rig until the rig's `.env` moves to the `:11440` URL plus the key.
Turn it on only alongside that rig-side `.env` change. The gateway remains available on `:11440`
for any client that wants the authenticated path today.
