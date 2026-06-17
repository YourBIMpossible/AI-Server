# WP-G — Advanced (optimistic, box-class)

Three independent sub-projects. Each is its own session. **Depends on:** WP-A; best on the 3090.

## G1 — Local Whisper meeting-notes

- `advanced/transcribe.py`: watch an inbox folder for audio; transcribe locally
  (faster-whisper, CUDA); write a cleaned, summarized note to `AI-Brain-Data/meeting-notes/`
  (summary via `aiserver`). Closes the "meeting transcription tool" item from the original plan.
- **Acceptance:** drop a short audio file → a transcript + summary note appears; runs on GPU.
- **Note:** writing into `AI-Brain-Data/` is the one sanctioned write — gate it behind an explicit
  `--write` flag and the backup-before-write rule in `system/SYSTEM-RULES.md`.

## G2 — Local coding-agent for bulk chores

- `advanced/coder/`: takes a repo path + a chore (e.g., "add docstrings", "scaffold pytest stubs
  for module X") and uses the coder model via `aiserver` to propose a diff; never auto-applies —
  writes a `.patch` for human review.
- **Acceptance:** produces a valid, reviewable patch for a sample module; applies cleanly with
  `git apply --check`.
- **Constraint:** proposal-only; no autonomous commits.

## G3 — QLoRA fine-tune on your voice (Phase 7 of the original plan)

- `advanced/finetune/`: build a dataset from `AI-Brain-Data/writing-samples/` + `decision-log/`;
  QLoRA-fine-tune a small base (7–8B) on the 3090 (24GB) so a local model writes in your voice;
  export GGUF + an Ollama `Modelfile`.
- **Acceptance:** the tuned model, served via Ollama, visibly matches your style on a held-out
  prompt vs the base (judged in the WP-F harness).
- **Constraint:** training data stays local; document the dataset build so it's reproducible.
