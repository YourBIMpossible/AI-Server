# Validation of the MyBuddy handoff (2026-09-16)

**Source:** `handoffs/MYBUDDY-HANDOFF-2026-09-16.md` — written by a separate chat session
during the pilot install; imported verbatim. **Method:** read-only probes over `ssh mybuddy`
the same day, after `decisions/2026-09-16__box-state-and-chat-ui-pilot.md`. Nothing changed.

## Confirmed

| Claim | Evidence |
|---|---|
| Ubuntu 26.04.1 LTS, LAN `192.168.1.128`, tailnet `100.89.51.34`, RTX 3090 24576 MiB | `/etc/os-release`, `ss`, `nvidia-smi` |
| Three UIs bound to loopback: `127.0.0.1:3000/3001/3080`; Ollama on `*:11434` | `ss -ltn`; all three answer HTTP 200 |
| `/srv/data` owned `zetard`, `/srv/models` owned `ollama` | `stat` |
| Compose `extra_hosts` pinned to `172.18.0.1` (Open WebUI) and `172.19.0.1` (AnythingLLM) | both files, mtimes 05:27 and 05:58 UTC |
| Bridge gateways `docker0 172.17.0.1`, `172.18.0.1`, `172.19.0.1` | `ip addr` — plus a fourth, `172.20.0.1` (LibreChat's `app_default`), which the handoff omits |
| Server keep-alive is "forever" | `OLLAMA_KEEP_ALIVE=-1` in the unit env; also `OLLAMA_CONTEXT_LENGTH=32768`, `MAX_LOADED_MODELS=2` |
| No `librechat.yaml` | still absent — answers the handoff's Priority-3 question: LibreChat has **no** chat provider configured |
| Model is cold now | `/api/ps` empty, 21 MiB VRAM. Matches the handoff's own before/after (`Keep alive: Forever` → `59 minutes`): the benchmark's per-request `keep_alive` overrode the server value |

## Corrections

1. **Model table has the wrong tag and wrong sizes.** There is no `gemma3:31b-it-q4_K_M`
   on the box; it is `gemma4:31b-it-q4_K_M`. The "Displayed UI size" column is the
   **parameter count** (32.9B, 31.3B…), not disk size. Actual on-disk: nemotron 25.4 GB,
   gemma4:31b 19.9, qwen3.8:27b 17.7, gemma4:26b-a4b 18.0, qwen3-coder 18.6, qwen2.5-coder 9.0,
   qwen3.5:9b 6.6, nomic 0.3.
2. **"Recommended normal usage" picks unscored models.** nemotron, qwen3.5:9b and the two
   coders have no WP-F eval score on this box. NORTHSTAR: model choice is a config line backed
   by a score. The evidence-backed pick remains `gemma4:26b-a4b-it-q4_K_M` (27/27). The
   handoff's table is a usage preference, not a decision — treat it as candidate list for the
   "score the four unevaluated models" roadmap item.
3. **SSH key auth already exists for the rig.** `authorized_keys` on the box carries
   `zeria@rig-to-mybuddy`, and `ssh mybuddy` logs in without a password. The handoff's tunnel
   (`ssh -N -L … zetard@192.168.1.128` + password) is the long form of

   ```powershell
   ssh -N -L 13000:127.0.0.1:3000 -L 13001:127.0.0.1:3001 -L 13080:127.0.0.1:3080 mybuddy
   ```

   Priority-1 step 1 is done; only the launcher wrapper is left.
4. **The API-key gateway is missing from the handoff's picture.** `aiserver-gateway.service`
   serves the OpenAI-compatible endpoint on `:11440` (loopback, LAN, tailnet) with a Bearer key.
   Every pilot UI bypasses it via raw `:11434`. Fine while loopback-only; not fine the moment a
   UI is exposed on LAN/tailnet (the handoff's "future access direction").

## Could not verify (root-only, no PTY for sudo)

- The two UFW rules (`/etc/ufw/user.rules` is `root:root 0640`, last modified 05:58 — consistent
  with the AnythingLLM rule being added then).
- `docker ps` status / restart policies. Container liveness confirmed by HTTP only.
- Whether `172.20.0.0/16` (LibreChat + `rag_api`) has a UFW allowance to `:11434`. If not,
  LibreChat's Ollama embeddings will fail silently even after a chat endpoint is wired.

## Routing

The handoff's "Recommended next work" is UX/ops on the rig and the pilot — none of it moves the
NORTHSTAR mission. Routed in `WORKLOG.md`: launcher + status scripts → Roadmap (pending the
pilot-placement call); Goose/agent harness → Needs your call (a new subsystem).
