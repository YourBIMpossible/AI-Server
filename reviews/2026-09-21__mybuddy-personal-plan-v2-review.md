# Review: MyBuddy updated personal plan (2026-09-21)

**Reviewed:** `mybuddy-updated-personal-plan-for-review.md`, supplied by the owner.
**Checked against:** the live box state recorded on 2026-09-21, and `NORTHSTAR.md`.

**Verdict:** the plan is sound and sized right. It needs four corrections, two of them in the
plan's own steps 1 and 7. Everything else can be used as written.

## Corrections

1. **Step 1: the history cleanup isn't fully achievable.**
   - Rewriting and force-pushing the PR #21 branch removes the bad commits from the branch.
   - It doesn't remove them from GitHub. The PR keeps its own copy of every pushed commit
     (`refs/pull/21/head`), and anyone who saw it can still see them.
   - The only complete purge is closing PR #21, opening a fresh PR from a clean branch, and
     asking GitHub Support to drop the old PR's cached commits.
   - Separately, `main` already contains the box IPs from earlier merged PRs. Step 1 covers
     only the unmerged branch.
   - Realistic options:
     - (a) Close #21, open a clean PR, and accept the leftover risk. Suggested: they're
       private-range and tailnet addresses, and the #671 notes contain no secrets.
     - (b) Also contact GitHub Support.
     - (c) Also rewrite `main`. That's disruptive to every clone.
2. **Step 7: a CPU model on the same Ollama will collide with the GPU model.**
   - The box runs one Ollama with `NUM_PARALLEL=1` and `MAX_LOADED_MODELS=2`.
   - With that setup, a "Quick MyBuddy" request makes your main chat wait in line behind it.
   - It also goes onto the GPU unless every request says `num_gpu: 0`.
   - The clean fix is a second, CPU-only runner instance on its own port, with the GPU hidden
     from it (`CUDA_VISIBLE_DEVICES=`) and bound to loopback.
   - The extra measurement that matters: does the main model's response speed drop while the
     CPU lane is busy? They share memory bandwidth.
3. **Step 3: stopping the UIs needs sudo.**
   - Your box user isn't in the `docker` group, so you run `docker compose stop` for each UI
     yourself, or add yourself to that group once.
   - Adding yourself to the group is effectively root access. On a personal box that's
     acceptable; just a conscious choice.
4. **Hardware name.**
   - The plan says 14900**KF**, while the repo records 14900**K**.
   - There's no practical difference here (the KF just lacks an iGPU, and the box is
     headless). Correct whichever is wrong.

## Fine as written

- **Step 2 (pin first, re-pin after scoring):** correct order.
- **Step 4 status script:** "selected model loaded" uses the runner's own status call. That's
  allowed in ops scripts and falls back to `unknown`.
- **Step 5:** tunnels through the `mybuddy` SSH alias, with no IP and no password.
- **Step 6:** keeping volumes and compose files is right.
- **"Revisit the bigger design" triggers:** these are the right tripwires.
- **NORTHSTAR:** no conflicts. Raw port 11434 accepted for personal use matches the 09-13
  closeout.

## Your call

- Step 1 method: option (a), (b) or (c) above.
- Step 3: add yourself to the `docker` group, or run the commands with sudo each time.
