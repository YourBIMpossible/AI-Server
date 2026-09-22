<!-- Imported verbatim from the owner's Downloads on 2026-09-16 (written by a separate chat session, not this repo). Validation against the live box: decisions/2026-09-16__handoff-validation.md -->

# MyBuddy Local AI Stack — Claude Code Handoff

**Prepared:** 2026-09-16

## Purpose

This document is a current-state handoff for Claude Code. It describes the local AI system called **MyBuddy**, what is installed and working, the Docker/networking fixes already made, how the Windows user currently reaches the services, what has been validated, and what should be improved next.

**Important operating principle:** Do not redesign or overwrite the existing setup based on assumptions. Inspect current files and live state first. The user wants a local-first, provider-agnostic AI system with multiple interfaces, controlled access to personal data, and supervised agent/tool use.

---

## Executive summary

MyBuddy is an Ubuntu server running local Ollama models on an NVIDIA RTX 3090. It hosts multiple Docker-based AI interfaces:

- **Open WebUI** — general local model chat.
- **AnythingLLM** — document/RAG-oriented workspace and local model chat.
- **LibreChat** — multi-provider chat / future agent-oriented UI.
- **Ollama** — host-level local model runtime.

All major services were confirmed running simultaneously on 2026-09-16. The earlier user-facing failures were primarily **Windows-to-MyBuddy access failures**, not proof that the applications could only run one at a time.

The Docker containers intentionally bind their web ports to `127.0.0.1` on MyBuddy. This is secure but means a browser on the user’s Windows PC cannot directly access them. The current working solution is an SSH tunnel from Windows to MyBuddy that maps local Windows ports to MyBuddy’s loopback-only web ports.

AnythingLLM was tested end-to-end successfully with Ollama and the selected local Nemotron model. The user saw a successful response in the AnythingLLM UI.

---

## User goals and constraints

### Goals

- Build a personal, local-first AI system called **MyBuddy**.
- Use local models as the default/control layer, but retain provider flexibility for external APIs such as OpenAI, Grok, and Gemini.
- Use multiple UIs intentionally rather than being locked into a single product:
  - AnythingLLM for documents/RAG and knowledge work.
  - LibreChat as a general/multi-provider assistant and possible agent frontend.
  - Open WebUI as a local model cockpit and chat interface.
- Eventually support supervised agents, MCP tooling, automation, and remote access.
- Access the system from Windows now and from phone/other devices later.
- Keep private/local data isolated by default. Deliberately choose what data can be exposed to external/cloud models.

### Important preferences

- The user wants to become an AI expert, **not** a Docker/networking/code expert.
- They have ADHD and need plain-language, short, highly reliable operating steps.
- Normal operation must become one-click or nearly one-click. They should not need to remember ports, Docker subnets, UFW rules, or SSH syntax.
- Do not respond with speculative instructions or repeat a failed instruction. Verify state before proposing changes.
- Clearly distinguish commands meant for **Windows PowerShell** versus the **MyBuddy Ubuntu terminal**.
- Do not make irreversible changes without confirming the exact intended action.

---

## Hardware and storage

### Server

- Hostname: `mybuddy`
- Ubuntu: `26.04.1 LTS`
- LAN IPv4 address: `<box-lan-ip>`
- Tailscale IPv4 address observed: `<box-tailnet-ip>`
- GPU: NVIDIA GeForce RTX 3090
- VRAM: 24 GB / `24576 MiB`

### Storage boundaries

The user wants strict separation of storage roles:

- OS/apps/Docker: OS volume.
- Persistent application data: `/srv/data`.
- Ollama model files: `/srv/models`.

Known ownership notes:

- `/srv/data` is owned by user `zetard`.
- `/srv/models` is owned by the `ollama` account.

Do not place application work files on the models drive. Preserve these boundaries when adding tools or volumes.

---

## Components and live service state

### Ollama

- Runs as a host system service, not in Docker.
- Service status was verified `active`.
- API verified working at:

```text
http://127.0.0.1:11434
```

- Ollama is listening on port `11434`.
- Confirmed endpoint:

```text
GET /api/tags
```

returned the installed model catalog.

### Docker containers

The following status was captured on 2026-09-16:

| Container | Status at audit | Host binding / port | Docker network | Restart policy |
|---|---|---|---|---|
| `mybuddy-open-webui` | Healthy | `127.0.0.1:3000 -> 8080/tcp` | `open-webui_default` | `unless-stopped` |
| `mybuddy-anythingllm` | Healthy | `127.0.0.1:3001 -> 3001/tcp` | `anythingllm_default` | `unless-stopped` |
| `LibreChat` | Up | `127.0.0.1:3080 -> 3080/tcp` | `app_default` | `always` |
| `rag_api` | Up | No host port published | `app_default` | `always` |
| `vectordb` | Up | Internal `5432/tcp` | `app_default` | `always` |
| `chat-mongodb` | Up | Internal `27017/tcp` | `app_default` | `always` |
| `chat-meilisearch` | Up | Internal `7700/tcp` | `app_default` | `always` |

Published ports observed with `ss`:

```text
127.0.0.1:3000  Open WebUI
127.0.0.1:3001  AnythingLLM
127.0.0.1:3080  LibreChat
*:11434          Ollama
```

### Important conclusion

All services can run concurrently. They are deliberately bound to MyBuddy loopback (`127.0.0.1`) rather than exposed to the full LAN. That design improves security, but it requires a tunnel or an intentional reverse-proxy/Tailscale-serving design for access from Windows or phones.

---

## Installed Ollama models

Models visible in Open WebUI / Ollama include:

| Model tag | Displayed UI size | Intended role |
|---|---:|---|
| `nemotron-3.5-lightning:30b-a3b-q4_K_M` | 32.9 GB | Main high-capability general assistant |
| `gemma3:31b-it-q4_K_M` | 31.3 GB | Large instruction-tuned general assistant |
| `qwen3.8:27b-q4_K_M` | 27.3 GB | Large general Qwen-family alternative |
| `gemma4:26b-a4b-it-...` | 25.8 GB | Large instruction-tuned general assistant; UI truncates full tag |
| `qwen3.5:9b` | 9.7 GB | Faster/lighter general chat |
| `qwen3-coder:30b-a3b-q4_K_M` | 30.5 GB | Large code-specialist model |
| `qwen2.5-coder:14b` | 14.8 GB | More practical/faster code-specialist model |
| `nomic-embed-text:latest` | 137 MB | Embedding model for retrieval/RAG, not chat |

### Recommended normal usage

- Everyday high-quality local chat: `nemotron-3.5-lightning:30b-a3b-q4_K_M`
- Fast/low-resource chat: `qwen3.5:9b`
- Routine coding/scripts/debugging: `qwen2.5-coder:14b`
- Hard coding/code review: `qwen3-coder:30b-a3b-q4_K_M`
- Document embedding/RAG: `nomic-embed-text:latest` paired with a chat model

---

## Benchmark results: Nemotron on RTX 3090

A direct Ollama benchmark was run against:

```text
nemotron-3.5-lightning:30b-a3b-q4_K_M
```

### Loaded model state before benchmark

```text
GPU: NVIDIA GeForce RTX 3090
GPU memory used: 22992 MiB / 24576 MiB
Ollama model placement: 12% CPU / 88% GPU
Ollama reported VRAM allocation: 22467680664 bytes
Context length: 16384 tokens
Keep alive: Forever
```

### Test results

| Test | Model-load time | Prompt tokens | Prompt evaluation | Prompt throughput | Output tokens | Generation throughput | Total time |
|---|---:|---:|---:|---:|---:|---:|---:|
| Short initial request | 5.31 s | 43 | 0.22 s | 191.43 tok/s | 128 | 147.90 tok/s | 6.40 s |
| Long warm prompt | 0.00 s | 9,693 | 3.94 s | 2,461.80 tok/s | 160 | 172.08 tok/s | 4.92 s |

### Post-test state

```text
GPU memory used: 22696 MiB
GPU utilization sampled: 55%
GPU memory utilization sampled: 49%
GPU power: 302.68 W
GPU temperature: 57 C
Ollama model placement: 14% CPU / 86% GPU
Ollama context: 32768 tokens
Keep alive: roughly 59 minutes
```

### Benchmark interpretation

- Performance is strong for a 32.9B-class Q4 model on an RTX 3090.
- The model is not fully GPU-resident; it uses partial CPU offload because it nearly fills 24 GB VRAM.
- Despite partial CPU offload, measured generation throughput was approximately 148–172 tok/s in the test.
- Long-prompt ingestion was approximately 2,462 tok/s.
- Model load added approximately 5.3 seconds on the first request; warm requests avoided that penalty.
- The system is suitable for responsive general chat and likely good document/RAG workflows.
- There is very limited spare VRAM. Avoid expecting multiple large models or unrelated heavy GPU workloads to coexist without impact.

### Caveat

The benchmark script printed blank response bodies despite showing valid timing/token metrics. This should be investigated with a simple direct `/api/generate` response test before relying on that script as a quality-validation benchmark. The AnythingLLM UI did successfully produce a visible answer from the same model.

---

## Docker-to-Ollama networking fixes

### Background

Ollama is host-level. Open WebUI and AnythingLLM are Docker containers on separate Docker bridge networks. Inside a container, `localhost`/`127.0.0.1` means the container itself—not the MyBuddy host.

Each container must therefore reach the host Ollama service through a host gateway mapping and must be permitted by UFW to reach TCP `11434`.

### Open WebUI

Compose file:

```text
/home/zetard/mybuddy-pilot/open-webui/compose.yaml
```

Docker network:

```text
open-webui_default
172.18.0.0/16
Gateway: 172.18.0.1
```

The prior generic Docker mapping resolved `host.docker.internal` to the wrong bridge gateway `172.17.0.1`.

The Compose mapping was changed from:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

to:

```yaml
extra_hosts:
  - "host.docker.internal:172.18.0.1"
```

Open WebUI’s Ollama environment value is:

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

UFW rule added:

```bash
sudo ufw allow from 172.18.0.0/16 to any port 11434 proto tcp comment 'Open WebUI Docker to Ollama'
```

The following was successfully tested from inside the Open WebUI container:

```text
http://host.docker.internal:11434/api/tags
HTTP 200
```

### AnythingLLM

Compose file:

```text
/home/zetard/mybuddy-pilot/anythingllm/compose.yaml
```

Docker network:

```text
anythingllm_default
172.19.0.0/16
Gateway: 172.19.0.1
```

The prior generic mapping again resolved `host.docker.internal` to wrong gateway `172.17.0.1`.

The Compose mapping was changed from:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

to:

```yaml
extra_hosts:
  - "host.docker.internal:172.19.0.1"
```

UFW rule added:

```bash
sudo ufw allow from 172.19.0.0/16 to any port 11434 proto tcp comment 'AnythingLLM Docker to Ollama'
```

AnythingLLM was recreated after the Compose edit:

```bash
sudo docker compose \
  -f ~/mybuddy-pilot/anythingllm/compose.yaml \
  up -d --force-recreate
```

Verified inside the container with Node’s built-in `fetch`:

```bash
sudo docker exec mybuddy-anythingllm \
  node -e "fetch('http://host.docker.internal:11434/api/tags').then(r => { console.log(r.status); return r.text() }).then(t => console.log(t.slice(0,300))).catch(e => { console.error(e); process.exit(1) })"
```

Result:

```text
200
{"models":[{"name":"nemotron-3.5-lightning:30b-a3b-q4_K_M", ...
```

### AnythingLLM UI settings

AnythingLLM configuration shown to work:

```text
LLM Provider: Ollama
Ollama model: nemotron-3.5-lightning:30b-a3b-q4_K_M
Ollama Base URL: http://host.docker.internal:11434
```

Important: `http://host.docker.internal:11434` is a **container-internal configuration value**. It is not a URL the user should open in a Windows browser.

AnythingLLM successfully answered:

```text
User: Are you there?
Model: Yes, I’m here! How can I help you today?
```

---

## Windows browser access: current method

### Why direct bookmarks failed

The applications are bound to MyBuddy loopback only:

```text
MyBuddy 127.0.0.1:3000 -> Open WebUI
MyBuddy 127.0.0.1:3001 -> AnythingLLM
MyBuddy 127.0.0.1:3080 -> LibreChat
```

A Windows browser’s `127.0.0.1` refers to Windows itself, not MyBuddy. Therefore a bookmark such as `http://127.0.0.1:13001` only works while an SSH local-forwarding tunnel is running on Windows.

### Verified working tunnel pattern

From **Windows PowerShell** (prompt should look like `PS C:\Users\Zeria>`), this command creates all three tunnels at once:

```powershell
ssh -N `
  -L 13000:127.0.0.1:3000 `
  -L 13001:127.0.0.1:3001 `
  -L 13080:127.0.0.1:3080 `
  zetard@<box-lan-ip>
```

After entering the MyBuddy password, the PowerShell window appears blank. That is expected: it is holding the tunnels open. If the window is closed or `Ctrl+C` is pressed, the browser links stop working.

### Windows bookmarks while tunnel is active

| UI | Windows browser URL |
|---|---|
| Open WebUI | `http://127.0.0.1:13000` |
| AnythingLLM | `http://127.0.0.1:13001` |
| LibreChat | `http://127.0.0.1:13080` |

### Current usability problem

The SSH-tunnel approach works but is not acceptable as the normal user workflow if it requires a visible PowerShell window, repeated password entry, or memorizing ports. The next implementation goal should be to make this one-click and robust.

---

## Tailscale: role and non-role

### Current facts

- MyBuddy has a Tailscale address: `<box-tailnet-ip>`.
- The Windows desktop and MyBuddy are on the same LAN today.

### Correct mental model

Tailscale is **not required** for the stationary Windows desktop to reach MyBuddy while both are on the same home LAN. The desktop can use MyBuddy’s LAN address:

```text
<box-lan-ip>
```

Tailscale is useful when the user wants access from a phone/laptop away from home, without opening router ports or exposing these web applications publicly.

### Future access direction

For a good remote phone/tablet experience, do not make the user manage SSH tunnels on mobile. Prefer a carefully designed private access path such as a reverse proxy limited to Tailscale, Tailscale Serve, or an equivalent approach—after security and user-experience design.

Do not expose the existing ports broadly to the internet.

---

## Key operational lessons

1. **Containers running does not prove browser access works.** Validate both MyBuddy-local service health and the actual Windows user path.
2. **Do not confuse Windows localhost with MyBuddy localhost.** `127.0.0.1` always means the computer where the browser/command is running.
3. **Do not enter `host.docker.internal` in the Windows browser.** It is used only by containers to reach MyBuddy’s host service.
4. **Do not assume Docker `host-gateway` is correct for every custom bridge network in this environment.** It resolved to `172.17.0.1`, while the relevant application networks used `172.18.0.1` and `172.19.0.1`.
5. **UFW needs per-subnet allowances** for each Docker bridge network that needs to reach host Ollama on port `11434`.
6. **Use exact verified ports.** AnythingLLM is MyBuddy `127.0.0.1:3001`, not `13001`; `13001` is only the chosen Windows tunnel port.
7. **Commands need a label.** Always say explicitly whether a command belongs in Windows PowerShell or MyBuddy Ubuntu terminal.
8. **The user should not need to remember infrastructure details.** Build a reliable launcher/control layer.

---

## Current architecture diagram

```text
                           Windows Desktop (same home LAN)
                           --------------------------------
                           Browser bookmarks:
                           127.0.0.1:13000  Open WebUI
                           127.0.0.1:13001  AnythingLLM
                           127.0.0.1:13080  LibreChat
                                      |
                                      | SSH local forwards over LAN
                                      | ssh -> zetard@<box-lan-ip>
                                      v
MyBuddy Ubuntu Server ------------------------------------------------
  loopback-only published ports:
    127.0.0.1:3000 -> mybuddy-open-webui:8080
    127.0.0.1:3001 -> mybuddy-anythingllm:3001
    127.0.0.1:3080 -> LibreChat:3080
                                      |
                         Docker bridge access to host Ollama
                                      |
         Open WebUI:    172.18.0.0/16 -> gateway 172.18.0.1
         AnythingLLM:   172.19.0.0/16 -> gateway 172.19.0.1
                                      |
                           host.docker.internal:11434
                                      |
                                      v
                            Ollama host service :11434
                                      |
                                      v
                         RTX 3090 local model inference
```

---

## Recommended next work: prioritize usability

### Priority 1: Create a one-click Windows access launcher

Goal: user should not manually enter the SSH command, retain a visible terminal window, remember tunnel ports, or retype the MyBuddy password for routine use.

Suggested path:

1. Establish Windows-to-MyBuddy SSH key authentication.
2. Use a passphrase-protected key plus Windows `ssh-agent`, or explain and obtain user agreement for an unencrypted private key if choosing convenience over that protection.
3. Create a small Windows launcher that:
   - starts the three local SSH forwards in the background;
   - checks that a tunnel is already running before duplicating it;
   - opens the three local bookmarks or a simple local menu;
   - gives a clear error if MyBuddy is offline/unreachable;
   - provides an equally simple “stop” command/shortcut if needed.
4. Prefer a hidden/background task rather than a visible persistent PowerShell window.
5. Test a full reboot/re-login workflow.

Potential tunnel targets are already verified:

```text
Windows 13000 -> MyBuddy 127.0.0.1:3000   Open WebUI
Windows 13001 -> MyBuddy 127.0.0.1:3001   AnythingLLM
Windows 13080 -> MyBuddy 127.0.0.1:3080   LibreChat
```

### Priority 2: Create simple MyBuddy health commands

Create short, documented commands/scripts such as:

```text
mybuddy-status
mybuddy-start
mybuddy-stop
```

Requirements:

- Plain-English output.
- Check Ollama API, container status, and published local ports.
- Clearly say which UI is unavailable and why.
- Do not make destructive changes.
- Store scripts in a predictable repository-controlled location.
- Avoid duplicating several conflicting control planes.

### Priority 3: Verify/recover Open WebUI and LibreChat functionality through the now-working tunnel

The services were running according to Docker state, but the user reported Open WebUI and LibreChat had stopped working in the browser. The immediate reason shown in screenshots was that no tunnel was active. After the all-in-one tunnel was started, the user reported success (“HAHA, that was it”).

Still, validate each UI after a normal reboot or fresh login:

- Open WebUI loads and can list/use Ollama models.
- AnythingLLM loads and reaches Ollama.
- LibreChat loads; identify and document its configured LLM provider and endpoint.

### Priority 4: RAG configuration in AnythingLLM

AnythingLLM chat via Ollama is proven. If/when document ingestion is desired:

- Configure Ollama embedding provider to:

```text
http://host.docker.internal:11434
```

- Select:

```text
nomic-embed-text:latest
```

- Keep document sources and persistent data within the intended `/srv/data` boundary.
- Validate on a non-sensitive test document first.

### Priority 5: Agent/harness layer, later

Open WebUI, AnythingLLM, and LibreChat are primarily interaction surfaces/frontends. They are not, by themselves, a complete agent harness.

A future supervised harness should include:

- an agent runtime (Goose is being considered);
- controlled MCP servers/tools;
- least-privilege workspace directory;
- explicit approval boundaries for changes;
- audit logs;
- restricted access to credentials, Docker socket, `sudo`, and sensitive data;
- local-first defaults with optional external providers.

Goose is a potential fit but should not be installed/configured until the current access workflow is made simple and stable.

---

## Useful existing diagnostic commands

These are reference-only; do not make the user run them routinely once a status script exists.

### MyBuddy: Docker/UI status

```bash
sudo docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Networks}}'
```

### MyBuddy: inspect actual published port for a container

```bash
sudo docker inspect mybuddy-anythingllm \
  --format '{{range $containerPort, $bindings := .NetworkSettings.Ports}}{{$containerPort}} -> {{range $bindings}}{{.HostIp}}:{{.HostPort}} {{end}}{{println}}{{end}}'
```

### MyBuddy: Ollama local health

```bash
curl -sS --max-time 5 http://127.0.0.1:11434/api/tags
```

### MyBuddy: loaded model and placement

```bash
ollama ps
curl -s http://127.0.0.1:11434/api/ps
```

### MyBuddy: GPU snapshot

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,temperature.gpu --format=csv,noheader,nounits
```

### MyBuddy: container-local Ollama test for AnythingLLM

```bash
sudo docker exec mybuddy-anythingllm \
  node -e "fetch('http://host.docker.internal:11434/api/tags').then(r => { console.log(r.status); return r.text() }).then(t => console.log(t.slice(0,300))).catch(e => { console.error(e); process.exit(1) })"
```

### Windows PowerShell: current working all-UI tunnel

```powershell
ssh -N `
  -L 13000:127.0.0.1:3000 `
  -L 13001:127.0.0.1:3001 `
  -L 13080:127.0.0.1:3080 `
  zetard@<box-lan-ip>
```

---

## Do not do without inspection/confirmation

- Do not overwrite the Compose files.
- Do not remove the existing explicit `host.docker.internal` gateway mappings without testing the replacement.
- Do not remove the two UFW rules that permit the specific Docker networks to reach Ollama port `11434`.
- Do not expose Open WebUI, AnythingLLM, LibreChat, Ollama, or SSH publicly to the internet.
- Do not bind the apps broadly to LAN interfaces without an agreed access/security design.
- Do not put application files or document databases on `/srv/models`.
- Do not grant an agent automatic `sudo`, Docker socket access, unrestricted filesystem access, or unreviewed external MCP tools.

---

## Success criteria for the next phase

The next phase is successful when:

1. After a normal Windows login and MyBuddy boot, the user can access each desired UI with a desktop shortcut or one clearly labeled action.
2. The user never needs to recall `127.0.0.1`, `13000`, `13001`, `13080`, `172.18.0.1`, `172.19.0.1`, or Docker/UFW commands for normal use.
3. The shortcut gives useful feedback if MyBuddy is off, unreachable, or an app is not healthy.
4. Open WebUI, AnythingLLM, and LibreChat remain independently usable at the same time.
5. The system remains local-first and does not expose AI web services publicly.
6. A future Tailscale-based remote access path is designed separately for phone/laptop use away from home.

---

## Final current-state statement

The MyBuddy local AI stack is operational. Ollama is healthy, the major containers are running concurrently, Docker-to-Ollama connectivity has been corrected for Open WebUI and AnythingLLM, AnythingLLM has successfully answered using the local Nemotron model, and performance testing showed strong warm inference throughput on the RTX 3090.

The dominant remaining issue is not model performance or container health. It is **user experience**: replace the manual Windows SSH-tunnel workflow with a secure, one-click access method and document the resulting simple routine.
