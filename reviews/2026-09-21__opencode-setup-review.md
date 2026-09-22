# OpenCode setup on the rig: read-only review (2026-09-21)

The owner opened this as a named read-only review, including the legacy `F:\AI-Dev` path.
Nothing was changed.

## What exists

| Location | What it is | State |
|---|---|---|
| `C:\Users\Zeria\.config\opencode\opencode.json` | **The config OpenCode actually uses** (global). Last changed Jul 25. | Points at `localhost:11434` on the rig, model `qwen3-coder-32k` |
| `F:\AI-Models Local\.opencode\` | Per-folder extras: 4 agents and 4 slash commands | Only active when OpenCode is started inside `F:\AI-Models Local` |
| `F:\AI-Dev\.tools\opencode\` | Start/Stop/Warm PowerShell launchers and icons | Rig-only, and hardcoded to the rig's local model server |
| `F:\AI-Models Local\OpenCode\` | Empty folder | Nothing to keep |

- The installed CLI is v1.18.5 (`%APPDATA%\npm\opencode.cmd`).
- It was last used 2026-08-21, per its log.
- The rig's own model server isn't running now.

## Findings

1. **It still points at the rig, not MyBuddy.**
   - `baseURL` is `http://localhost:11434/v1`, and the rig's model server is off.
   - So OpenCode doesn't work today; it has nothing to talk to.
   - Moving it to MyBuddy is a one-line change: point it at the gateway (`:11440`, needs the
     key) or at a tunnel.
2. **Its model doesn't exist on the box.**
   - `qwen3-coder-32k` was a custom 32k-context copy made on the rig.
   - The box has `qwen3-coder:30b-a3b-q4_K_M`, and the box's server already runs every model at
     32k.
   - The config's label on that tag, "256k ctx - slow", is wrong for the box.
3. **Loading a coding model would push gemma4 out.**
   - gemma4 (17 GB) plus qwen3-coder (18 GB) don't fit together in 24 GB.
   - Using qwen3-coder breaks the plan's "one model during normal use" rule. It would unload
     gemma4, or spill onto the CPU.
   - Two ways out:
     - (a) Use gemma4 for coding too. It scored 27/27 on the tool-calling eval cases, while
       qwen3-coder scored 22/27 on 09-13.
     - (b) Accept that model swaps happen while coding.
   - Evidence favors (a).
4. **The launchers are rig-era, and one of them is harmful on the box.**
   - `Warm-Model.ps1` and `Stop-OpenCode.ps1` load and unload models on `localhost`.
   - On the box, Stop's `keep_alive: 0` would evict whatever model is loaded, gemma4 included.
     Don't reuse them.
   - `Start-OpenCodeWeb.ps1` (a local web UI on `127.0.0.1:4096`, reusing a running server) is
     fine to keep, minus the warm step.
5. **The agents and commands are sound but tied to a legacy file.**
   - Each agent points at `F:\AI-Dev\tools-ai-collab\session-protocol.md`, which is in the
     legacy area.
   - They still work, because the rules are written inline in each file.
   - They load only in `F:\AI-Models Local`. To use them everywhere, they'd move to
     `~\.config\opencode\`.
6. **Tool calls need a model that does them well.**
   - `qwen2.5-coder:14b` is correctly marked `tool_call: false`.
   - OpenCode is an agent, and it's only useful with tool calls.
7. **No credentials are stored.** The config has no API keys, which is good. The gateway route
   would add one; keep it in an environment variable, not in the JSON.

## Security note

OpenCode can edit files and run commands on the rig. That trips the plan's "revisit the bigger
design" trigger for agents, so decide before wiring it to MyBuddy:

- **Where it runs.** It runs on the rig, never on the box.
- **What it may touch.** A repo worktree, per the parallel-sessions house rule.
- **Whether command approval stays on.** OpenCode's `permission` settings control this; they
  aren't set here, so defaults apply.

## Smallest path to "OpenCode uses MyBuddy"

1. Add a `mybuddy` provider to the global config:
   - Base URL: the gateway address through the `mybuddy` host, or a tunnel to `11434`.
   - Model: `gemma4:26b-a4b-it-q4_K_M`.
   - Key: read from an environment variable.
2. Set `permission` for edit and bash to `ask`.
3. Drop the rig-model warm/stop scripts.

That's an additive plan item. It isn't built; it's waiting for the owner's go-ahead.
