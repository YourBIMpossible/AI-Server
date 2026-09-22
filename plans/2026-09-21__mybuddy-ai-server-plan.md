# MyBuddy — personal plan

**Rewritten 2026-09-21.** MyBuddy is a personal system for one person, not a product. There
are no other users, no customers and no fleet, so there's no process built for any of them.
The mission is still `NORTHSTAR.md`: one private local endpoint whose model choice rests on
measurements.

## Where it stands

- **Box:** `ssh mybuddy`, RTX 3090. The endpoint has been live and passing since the 09-13
  closeout.
- **Model:** `gemma4:26b-a4b`, scored 27/27.
- **Chat UIs:** Open WebUI, AnythingLLM and LibreChat run on the box. They're reached only
  over an SSH tunnel and talk to Ollama directly. That's fine for one user.

## Do next (in order)

1. **Tidy the box.**
   - Merge PR #21.
   - `git pull` in `~/AI-Server`.
   - Delete the three merged worktrees.
   - Move `ai_stress_test.csv` and `ollama-benchmark.py` out of `~`.
2. **Score the four unscored models** (`gemma4:31b`, `qwen3.8:27b`, `qwen3.5:9b`,
   `nemotron-3.5-lightning`).
   - **Stop the chat UIs first,** so the scores aren't skewed by a shared GPU.
   - Change `config/models.txt` only if one beats gemma4.
3. **A status script.** `mybuddy-status` prints in plain English whether the model server, the
   gateway and each UI are up.
4. **A one-click shortcut on the PC.** A desktop shortcut that opens the SSH tunnel and the
   browser, and says "box offline" when it can't connect.
5. **Pick a UI.**
   - Use them for a week or so.
   - Keep the one you like and stop the others.
   - Write one line in `WORKLOG.md` saying which one and why.
6. **Set every UI to the same model,** so none of them loads a second model and pushes the
   main one out of GPU memory.

## Optional (only if it starts to bother you)

- **Scheduled acceptance test:** it fails because system Python lacks `sqlite_vec`. The fix
  needs a small venv for AI-Server. Skip it unless you want that test running on its own.
- **Route the UIs through the gateway on port 11440, then close port 11434 to the LAN:**
  tidier, but it doesn't change who can reach the box. That's you and your tailnet either way.
- **Document search (RAG):** before indexing anything, write a short list of the folders
  that are allowed and the folders that never are.

## Parked

- Goose and agents, a separate "Personal AI Workspace" project, cloud routing, a dashboard
  card, and a CI lane for BIMpossible.

## House rules

- Never port-forward the box to the internet.
- No client or work-for-hire data on the box.
- The public AI-Server repo gets no IPs, keys or private-project details.
