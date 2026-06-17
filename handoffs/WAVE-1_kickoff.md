# Wave-1 kickoff — paste into a Claude Code session at `F:\AI-Dev\AI-Server\`

You are building the local-LLM automation platform described in `PROGRAM_PLAN.md`. Follow
`CLAUDE.md` (and the canonical `system/WORKING-STYLE.md` + `system/SYSTEM-RULES.md`). Tests +
each handoff's acceptance criteria are the definition of done. Work in small, verifiable steps;
run `PYTHONPATH=. python -m pytest -q` after each change.

## Starting point (already in the repo)

- The `aiserver/` package skeleton is scaffolded and its tests pass: `config` (merge order +
  overrides), `client` (chat + embeddings against a mock endpoint), and the endpoint-down error.
  Confirm first with `PYTHONPATH=. python -m pytest -q`.
- `scripts/smoke-test.py` and `automation/daily_digest.py` still use inline loaders — that's the
  WP-A refactor target.

## Git workflow — branch + PR per work package

`main` is protected, so **no direct commits to it**. For each work package:

1. Branch: `git checkout -b wp-a-core-library` (one branch per WP — for parallel sessions, one branch each).
2. Build to the handoff's acceptance criteria, committing in small steps; run `PYTHONPATH=. python -m pytest -q` before each commit.
3. Push + open a PR: `git push -u origin <branch>`, then `gh pr create --fill --base main`.
4. Wait for CI (the test matrix) to go green, then merge: `gh pr merge --squash --delete-branch`.
5. Start the next WP from fresh main: `git checkout main && git pull`.

Do WP-A's branch/PR first (everything depends on it). After it merges, WP-B and WP-C can run in parallel on their own branches.

## Do this, in order

1. **Finish WP-A** (`handoffs/WP-A_core-library.md`): refactor `smoke-test.py` and
   `daily_digest.py` to import `aiserver` (no inline `.env`/HTTP), move the digest prompt into
   `aiserver/prompts.py`, and wire `aiserver/log.py`. Behaviour identical; tests stay green.
2. **Then split into the wave.** WP-B, WP-C, and WP-D/D2 (PC-Monitor) are independent. Single
   session: do WP-C (automation framework) → WP-B (RAG) → WP-D. Parallel sub-agents: run WP-B and
   WP-C concurrently after WP-A.
3. For each WP, open its `handoffs/WP-*.md`, build to its acceptance criteria, add its tests, and
   stop at its "Out of scope" line.

## Guardrails

- Portability is hard law: hosts/models/paths live in `.env`/`config/`, never in code.
- Talk to the model only via the OpenAI-compatible API — never shell out to the `ollama` CLI.
- Automations are read-only on `AI-Brain-Data/` and `BIMpossible_Workspace/`; outputs go to `out/`.
- Never expose the endpoint publicly.

## Done when

WP-A, WP-B, and WP-C are each merged to `main` via green PRs, and WP-B + WP-C produce files under
`out/` against a mock endpoint. That — plus a WP-F eval pass — is your PC-build green light.
