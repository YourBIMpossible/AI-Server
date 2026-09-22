# MyBuddy forward plan: review (2026-09-21, personal scale)

**Replaces** the earlier production-style review. Its rubric, network redesign, gate register
and governance templates were sized for a product, and MyBuddy is a personal system.

**Verdict:** the plan is sound. The personal version is `plans/2026-09-21__mybuddy-ai-server-plan.md`.

## Facts checked on the box (2026-09-21)

- The endpoint and gateway are up.
- Ollama is set to keep models loaded (`KEEP_ALIVE=-1`) and allows up to two loaded at once
  (`MAX_LOADED_MODELS=2`). This is why step 6 matters: a UI set to a different model can load a
  second one.
- The UIs listen on loopback only and talk to Ollama directly.
- The containers can't reach the gateway on port 11440 as currently configured. That only
  matters if you choose the optional "route through the gateway" item. Pointing them at the
  box's LAN address is the simple way.
- The box checkout is 6 commits behind, and the merged worktrees and two loose files are still
  there.
- There's no AI-Server venv, so the scheduled acceptance test can't find `sqlite_vec`. That
  fix is listed as optional.

## One thing that really matters

Stop the chat UIs before scoring models. Otherwise the scores measure a shared GPU.

## Open item

- Public-repo history still contains the box IPs and the #671 notes pushed earlier. Scrubbing
  them means rewriting the branch history, which is your call. The current files are clean.
