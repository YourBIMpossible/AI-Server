# Relocating AI-Server to the 3090 box

The design goal: moving inference to the dedicated box is a **config change, not a rebuild**.
Your automations keep running on your main rig (that's where the files are); only the
inference endpoint moves.

## One-time, on the 3090 box

1. **OS + driver:** install Ubuntu Server LTS, the NVIDIA driver, and CUDA. (See the build
   plan: `AI-Brain-Data/_status/AI-Server_Build_and_Integration_Plan.md`.)
2. **Copy this repo** to the box (git clone, or copy the `AI-Server/` folder).
3. **Install + serve:**
   ```bash
   bash scripts/setup-linux.sh
   ```
   Installs Ollama, binds it to the LAN (`0.0.0.0:11434`), pulls the models in
   `config/models.txt`, and smoke-tests it.
4. **Step the model up** for 24GB: edit `.env` → `MODEL=qwen2.5-coder:32b` (or
   `llama3.3:70b`), then `ollama pull <that model>`.

## On your main rig (the only change to your automations)

Edit `.env`:

```
OLLAMA_HOST=http://<box-hostname-or-tailscale-name>:11434
```

That's it. `daily_digest.py` (and every future automation) now runs on the box's GPU.
Re-run `register-tasks-windows.ps1` only if you changed the schedule.

## Networking & security

- Prefer **Tailscale**: install it on both machines and use the box's Tailscale name as
  `OLLAMA_HOST`. Avoids exposing the endpoint to your whole LAN, and works off-network.
- **Never port-forward 11434 to the public internet.**
- If you want auth, put Caddy in front of Ollama and require an API key.

## Newest models on the box

The latest Qwen3.6 GGUFs don't load in Ollama yet (vision-file issue). To run them on the
box, use **llama.cpp** (or Unsloth) with their UD-Q4_K_XL quant, served on the same
`:11434` OpenAI-compatible shape — your automations won't know the difference.
