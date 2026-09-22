# MyBuddy — Updated Personal Plan

**Status:** adopted 2026-09-21 (owner-approved, with the corrections from `reviews/2026-09-21__mybuddy-personal-plan-v2-review.md`). Mission stays `NORTHSTAR.md`.

## What MyBuddy is

MyBuddy is your private, one-person local AI system. It is not a public product, a fleet, or a multi-user platform.

The goal is simple:

> A local AI box you can open easily, talk to every day, and improve only when a real need appears.

The system already has a working local endpoint, an RTX 3090 for primary AI inference, an Intel 14900KF for supporting work, and three chat interfaces being tried in real use:

- Open WebUI
- AnythingLLM
- LibreChat

Do not add complexity merely because the hardware can support it. Use each part of the machine for a job that helps the normal MyBuddy experience.

---

## Current decisions

These are the working decisions for this personal plan.

| Topic | Current decision |
|---|---|
| Primary inference | RTX 3090 runs the main interactive model |
| CPU role | Intel 14900KF supports the system now and may later run a measured small-model/background-work lane |
| UI location | Keep Open WebUI, AnythingLLM, and LibreChat on MyBuddy for now |
| Daily UI | Not chosen yet; use the three UIs naturally before choosing |
| UI model behavior | All UIs stay pinned to one selected model during testing and normal daily use |
| Gateway `:11440` | Keep available; routing UIs through it is optional for the current single-user setup |
| Raw Ollama `:11434` | Accepted temporarily for the private personal setup; revisit before broader access or sensitive/new workloads |
| RAG/document search | Not yet; first decide allowed and forbidden folders |
| Goose/agents/MCP | Parked until there is a real agent job worth doing |
| Cloud/external routing | Parked |

---

## Do next, in order

## 1. Clean the records and box

Before merging or bringing PR #21 into `main`:

- History cleanup, owner-approved option (a): PR #21 is closed unmerged and replaced by a fresh PR from a clean branch carrying only the final records. GitHub's cached copy of #21 and older IPs already in `main` are accepted residual risk (private-range addresses; no secrets).
- Merge the clean PR.
- Update `~/AI-Server` to the selected clean revision.
- Remove old merged worktrees.
- Archive loose benchmark files from the home directory, including `ai_stress_test.csv` and `ollama-benchmark.py`.
- Update old `WORKLOG` “Needs your call” entries so they point to this personal plan or say resolved/deferred; do not leave contradictory gates behind.

**Result:** the repository and the box tell one simple, current story.

---

## 2. Pin one model in every UI

Before any model comparison or week-long UI trial:

- Confirm exact installed model tags with `ollama list`.
- Keep the current selected model as the temporary shared model unless the exact tag has changed.
- Configure Open WebUI, AnythingLLM, and LibreChat to use that same model only.
- Avoid loading a different large model from one UI while another UI is open.

Why this matters:

- The RTX 3090 has 24 GB VRAM.
- A second large model can consume VRAM, trigger CPU offload, evict the main model, or make responses inconsistent.
- A fair UI comparison requires the same model behind each UI.

**Result:** predictable GPU behavior and an honest comparison.

---

## 3. Score the unscored models fairly

Compare the four remaining model candidates only after the UIs are stopped temporarily.

- Stop the UI containers for the scoring session so they do not share GPU memory or change model residency. (Owner is in the `docker` group, so no sudo per command.)
- Use the exact model tags returned by `ollama list`; do not use shortened or guessed names in scripts.
- Run the established evaluation against the current selected model and the four unscored candidates.
- Change `config/models.txt` only if a challenger actually beats the current model under the same test.
- Record the outcome in one short decision note: selected model, measured result, date, and why it won.

After scoring, set all three UIs to the measured winner before using them normally again.

**Result:** the main MyBuddy model is selected by evidence, not by model size, hype, or first impressions.

---

## 4. Make MyBuddy easy to check

Add one plain-English command:

```text
mybuddy-status
```

It should say only what you need for daily use:

```text
MyBuddy model server: online / offline
MyBuddy gateway: online / offline
Open WebUI: online / offline
AnythingLLM: online / offline
LibreChat: online / offline
Selected model: loaded / not loaded / unknown
```

Requirements:

- No Docker subnet details in normal output.
- No stack traces in normal output.
- If a check cannot run, say `unknown` and explain in one short sentence.
- A later diagnostic mode may exist, but it is not the normal workflow.

**Result:** you can tell whether MyBuddy is ready without remembering Docker, ports, firewall rules, or terminal troubleshooting.

---

## 5. Make MyBuddy one click from Windows

Create a Windows desktop shortcut after the basic status path is proven.

The shortcut should:

1. Use the existing SSH host configuration for `mybuddy`; do not hardcode a live IP address.
2. Start or reuse the required background SSH tunnel(s).
3. Open the chosen MyBuddy UI in the browser.
4. Clearly say `MyBuddy is offline or unavailable` if it cannot connect.
5. Store no password in the shortcut or script.
6. Avoid leaving a visible PowerShell window open during normal use.

The current conceptual local browser addresses are:

```text
Open WebUI:    http://127.0.0.1:13000
AnythingLLM:   http://127.0.0.1:13001
LibreChat:     http://127.0.0.1:13080
```

**Result:** MyBuddy feels like an app, not a home-lab procedure.

---

## 6. Use the UIs, then choose a daily one

For about one week, use Open WebUI, AnythingLLM, and LibreChat for real everyday tasks using the same selected model.

Pay attention to simple questions:

- Which one do you naturally open first?
- Which one is clearest when something goes wrong?
- Which one handles conversations the way you think?
- Which one is least annoying to start, organize, and return to?
- Which one makes model switching, saving work, and basic chat feel easiest?

At the end of the week:

- Choose one as the **daily MyBuddy UI**.
- Write one short line in `WORKLOG.md` saying which one you chose and why.
- Stop the other UI containers if you do not need them every day.
- Keep their Compose files and Docker volumes. Do not delete anything until you are certain.

A daily choice does not mean the other UIs are failures. One may later be useful for a specific job, such as document work or testing models.

**Result:** the cockpit is selected from lived experience, not a feature checklist.

---

## 7. Give the CPU a useful supporting role

The RTX 3090 remains the primary interactive AI engine. The Intel 14900KF should not be forced to run the same large daily chat model just to raise utilization.

Instead, after Steps 1–6 are working smoothly, run one small, measured CPU-lane experiment.

### Run it as a separate CPU-only instance

The main runner handles one request at a time (`NUM_PARALLEL=1`), so a CPU model on the same instance would queue main chat behind it and would land on the GPU unless every request forces CPU. Run the CPU lane as a second runner instance on its own loopback port with the GPU hidden (`CUDA_VISIBLE_DEVICES=`). Also measure whether main-chat speed drops while the CPU lane is busy — they share memory bandwidth.

### Test one small CPU-resident model

Pick one smaller local model—using its exact installed tag—and test it as a possible "Quick MyBuddy" or background worker.

Possible jobs:

- Short rewrites, lists, extraction, and classification.
- Background summaries of approved non-sensitive text.
- Simple structured-output work such as JSON/table conversion.
- Small offline helper tasks while the RTX 3090 remains ready for main chat.
- Later, document chunking/embedding preparation if RAG is approved.

Measure:

- Cold-load time.
- Warm first-response delay.
- Prompt-processing speed.
- Generation speed.
- System RAM use.
- CPU use, power, and temperature.
- Whether the main GPU model stays loaded and responsive at the same time.

Keep the CPU model only if it earns a named role without making normal MyBuddy use worse.

### Desired future division of labor

```text
RTX 3090
└── Main MyBuddy model: high-quality interactive chat and hard tasks

Intel 14900KF + system RAM
├── Optional Quick MyBuddy: small CPU model for light utility work
├── Background/offline summaries and classification
├── Embedding/document preparation when RAG is approved
├── Evaluation tools, health checks, Docker, databases, and orchestration
└── Future supervised automation support
```

**Result:** the CPU contributes useful independent capacity without competing with the GPU’s best job.

---

## Optional later

These are useful only when you have a reason to need them.

### Scheduled acceptance test

System Python lacks `sqlite_vec`, so unattended acceptance needs a small dedicated AI-Server virtual environment.

Do this when you want regular unattended endpoint validation. Skip it for now if manual checks are enough.

### Route UIs through gateway `:11440`

Route UI traffic through the authenticated, OpenAI-compatible gateway and then restrict raw Ollama `:11434`.

This is optional for the current one-user, SSH-tunneled UI setup. It is still more isolated than direct raw Ollama because it adds authentication and a stable client contract, and it reduces what devices on the home LAN can call directly.

Revisit it before adding agents, external consumers, sensitive data, another user, or broader access.

### Document search / RAG

Before indexing anything, write a short list of:

- Folders MyBuddy is allowed to read.
- Folders MyBuddy must never read.
- How to remove indexed data if you change your mind.

No client or work-for-hire data goes on MyBuddy under this personal plan.

---

## Parked

Do not build these until there is a clear job and a separate decision to do so:

- Goose, agents, and MCP tools.
- Cloud or external-model routing.
- A separate workspace/product project.
- Dashboard status-card work.
- BIMpossible CI integration.
- Broad external access or public exposure.

---

## When to revisit the bigger design

Return to the stronger gateway, data, access, logging, and permission design before adding any of the following:

- An agent or MCP tool that can write files, run commands, use Git, browse, access GitHub, or control other software.
- Cloud/external model routing.
- Client data, work-for-hire data, personal sensitive documents, or any data under an NDA.
- Another regular user or another device with independent access.
- Unattended automation that can modify files, systems, or records.
- Broad LAN exposure, remote access beyond the current private setup, or any public exposure.

---

## House rules

- Never port-forward MyBuddy to the public internet.
- Do not put client or work-for-hire data on MyBuddy.
- The public AI-Server repository gets no live IP addresses, API keys, credentials, or private-project information.
- Use exact installed model tags when configuring or testing Ollama.
- Keep large-model GPU use deliberate: one selected main model during normal use unless a measured reason says otherwise.
- Keep changes small, reversible, and documented in plain language.

---

## Definition of success

This phase is done when:

1. You can click one shortcut and open MyBuddy from Windows.
2. You can run `mybuddy-status` and understand immediately whether it is ready.
3. One measured model is selected as the main model.
4. One UI is selected as your daily UI based on actual use.
5. The other UIs are safely preserved but no longer add daily complexity.
6. The RTX 3090 handles the main interactive model reliably.
7. The 14900KF has either earned a useful supporting role through measurement or remains available without being forced into unnecessary work.
