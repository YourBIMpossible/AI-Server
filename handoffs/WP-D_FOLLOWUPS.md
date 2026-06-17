# WP-D — owed live validation & follow-ups

WP-D is built and verified to the mock/unit bar. The items below are **deliberately owed** —
this build environment has no GPU/Ollama and can't push the dashboard. Honest framing:
**mechanisms done; production validation owed.** None of these block anything; all are safe.

## D1 — Dashboard AI-Server card  (mechanism done, deployment owed)

Helper `scripts/aiserver_status.py` is merged (PR #5); the Dashboard `REFRESH-SPEC.md` is updated
locally + backed up but **unpushed**. It goes live on the next refresh:

- [ ] Run the next Dashboard refresh on the box (it now runs `aiserver_status.py` per the spec).
- [ ] Confirm the AI-Server card shows endpoint up/down + models + the three job summaries.
- [ ] `push-dashboard.ps1` to publish to Pages.

## D2 — PC-Monitor Inference card  (dark-launched, live validation owed)

**OFF by default — the current rig is unaffected until you opt in.** To validate on the AI box:

- [ ] Set `ollama.enabled: true` in PC-Monitor `config.json`.
- [ ] Restart the PC-Monitor collector with at least one model loaded.
- [ ] Open `:8787` and confirm the Inference card shows real `/api/ps` data (model + VRAM).

Safe to ignore: default-off means zero impact on the running collector until you purposely
enable it and restart.

## D3 — Revit weekly local engine  (writer-side flag; opt-in cutover)

`AI-Brain-Data/Revit-AI/process_revit_logs.py` now has `--engine deterministic|local`
(default `deterministic` = byte-identical, proven against the original). Local mode writes the
**canonical** weekly file via the local LLM, with a deterministic fallback if Ollama is down.

- [ ] `python process_revit_logs.py --engine local` with Ollama up — review the narrative.
- [ ] When happy, cut over: edit the G:-hosted `SKILL.md` "Execute:" line to
      `python3 process_revit_logs.py --engine local`.

Notes:
- **Fixed a pre-existing bug:** the script had 554 trailing NUL bytes (non-importable Python —
  the weekly task was silently broken). Stripped; real code untouched; original backed up under
  `Revit-AI/_backups/`.
- Disposition of the parallel `revit-weekly` AI-Server job (PR #6 → `out/revit-weekly/`):
  superseded for the canonical slot by the writer-flag; kept as an optional `out/` feed unless
  you want it removed.
