# Relocating AI-Server to the 3090 box

Your automations keep running on your main rig (that's where the files are); only the
inference endpoint moves.

> **Corrected 2026-09-10.** This doc used to say relocation was "a config change, not a
> rebuild" and that the endpoint setting was the only line that changes. That was wrong in a way
> that matters: the *serving-layer* environment — flash attention, context length,
> keep-alive — lives on the host running Ollama, is not carried by `.env`, and is worth up
> to ~150× on prefill. `scripts/setup-linux.sh` now sets it. The rig-side change really is
> one line; the box-side setup is not. See
> `decisions/2026-09-10__box-build-reassessment.md`.

## One-time, on the 3090 box

0. **BIOS first — before installing anything.** Non-negotiable for an always-on 14900K:
   update to a **microcode 0x12B+** build, and set the **Intel Default** power profile
   (not unlimited multi-core enhancement). 13th/14th-gen Intel had a voltage-degradation
   issue; an always-on inference box is exactly the duty cycle that surfaces it.
1. **OS + driver:** Ubuntu Server **26.04 LTS**, headless. Then the NVIDIA driver — check
   `ubuntu-drivers devices`, and install the branch explicitly via apt rather than
   `ubuntu-drivers install`, which has been reported to refuse the recommended branch on
   26.04. If you want the Docker path, the NVIDIA Container Toolkit needs Docker ≥26, and
   `nvidia-ctk runtime configure` must be re-run after every driver update or `--gpus`
   breaks.
2. **Copy this repo** to the box (git clone, or copy the `AI-Server/` folder).
3. **Install + serve:**
   ```bash
   bash scripts/setup-linux.sh
   ```
   Installs Ollama, writes the service override (LAN bind **plus** flash attention, 32k
   context, keep-alive), prints the server's effective config, pulls the models in
   `config/models.txt`, and smoke-tests it.
4. **Check the banner before you trust anything.** The script prints what the *service*
   sees. `OLLAMA_FLASH_ATTENTION` must be true and `OLLAMA_CONTEXT_LENGTH` 32768. A
   shell's view of the environment is not the service's — that mismatch has already cost
   one full measurement batch.
5. **Then pick the 24GB model on evidence** — see the notes in `config/models.txt`. Don't
   copy a model name out of a three-month-old doc; that is how the last set went stale.
6. **Install Tailscale now, even if you're staying LAN-only for a while:**
   ```bash
   bash scripts/setup-tailscale.sh
   ```
   Installs Tailscale, brings the tailnet up (`--ssh` included, since this box won't have
   a monitor attached for long), and firewalls `:11434` to the LAN subnet + tailnet
   interface via `ufw` — the piece that was overdue regardless of which address you end up
   using, since `setup-linux.sh` binds `0.0.0.0`. Do this while you're already at the
   keyboard; the alternative is a second trip to a headless box later. It changes nothing
   about how the endpoint answers until you edit `.env` on the rig (next section) — the
   LAN address keeps working exactly as it did before.

## On your main rig (the only change to your automations)

Edit `.env`:

```
INFERENCE_BASE_URL=http://<box-hostname-or-tailscale-name>:11434/v1
```

Use the LAN IP (or a router DHCP reservation, so it doesn't move) while you're testing
on-network; switch to the box's tailnet name — printed at the end of
`setup-tailscale.sh` — whenever you want this to keep working off-network too. Same repo,
same script, no rebuild either way.

That's it. `daily_digest.py` (and every future automation) now runs on the box's GPU.
Re-run `register-tasks-windows.ps1` only if you changed the schedule.

## Networking & security

- **Tailscale is installed in step 6 above regardless.** Whether `INFERENCE_BASE_URL`
  actually points at the tailnet name or the LAN IP is a separate decision, made whenever
  you want it, by editing one line in `.env` — see above. Tailscale avoids exposing the
  endpoint to your whole LAN and works off-network; on Windows, install it from
  https://tailscale.com/download and sign in with the same account.
- **Never port-forward 11434 to the public internet.**
- If you want auth, put Caddy in front of the endpoint and require an API key; set that key as
  `INFERENCE_API_KEY` on the rig.

## Newest models on the box

Qwen3.6 GGUFs with an mmproj still don't load in Ollama as of 2026-09-10 (ollama#14730,
#15898, both open); text-only variants work. If you need one Ollama can't serve, run
**llama.cpp** on the same `:11434` OpenAI-compatible shape — your automations won't know
the difference. Note llama.cpp is leaner and faster for a single user, but its tool-calling
grammar path has open defects on complex JSON Schema, so re-test opencode if you switch.

**vLLM is no longer on the roadmap for this box.** The old plan said "Ollama now, vLLM
later for concurrency." The 3090 is Ampere — no FP8 hardware support — so it gets none of
what vLLM's recent work optimizes for, while still paying its VRAM overhead on a card
where 24GB is the binding constraint. This is a single-user box; there is no concurrency
to win. Revisit only if that stops being true.
