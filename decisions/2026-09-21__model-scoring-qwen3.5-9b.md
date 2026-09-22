# Model scoring: gemma4:26b stays the main model (2026-09-21)

**Plan step 3** of `plans/2026-09-21__mybuddy-ai-server-plan.md`.

**Selected model:** `gemma4:26b-a4b-it-q4_K_M`. Unchanged; `config/models.txt` not edited.

## What ran

- The box's WP-F eval (`python -m eval.run`, 27 cases), judge `qwen3-coder:30b-a3b-q4_K_M`
  (same judge as 09-13).
- All three chat UIs were stopped for the whole session, and the GPU was empty at the start.
- `gemma4:26b-a4b-it-q4_K_M` was re-run in the same session as a control.

## Results

| Model | Pass | Long tier | long-digest-ops | long-extract |
|---|---|---|---|---|
| `gemma4:26b-a4b-it-q4_K_M` (control) | **27/27** | 4/4 | pass, 27.9 s | 27.4 s |
| `qwen3.5:9b` | 26/27 | 3/4 | **empty response**, 63.7 s | 56.8 s |

- qwen3.5:9b's failure is the known empty-response mode (tool_choice with a large system prompt).
- qwen3.5:9b was also slower on the hard and long cases, despite being the smaller model.
- Judge calibration was 6/8 on both runs. It is flagged unreliable on two paraphrase cases,
  but no verdict here depends on the judge: both results are keyword/tool-scored except one
  judged pass that both models share.

## Why only these two

The plan listed four "unscored" models. Three of them were already scored cleanly on
2026-09-13, before the UIs existed (`decisions/2026-09-13__wp-f-eval-separates-models.md`):

| Model | Score |
|---|---|
| `qwen3.8:27b-q4_K_M` | 27/27 |
| `nemotron-3.5-lightning:30b-a3b-q4_K_M` | 27/27 |
| `gemma4:31b-it-q4_K_M` | 26/27 |

All three were slower than gemma4:26b on long cases, and neither of the two 30B+ models fits
fully on the GPU at 32k. The eval is saturated at the top, so re-running them would add
nothing. Only `qwen3.5:9b` was truly unscored.

## Why gemma4:26b wins

It is tied for the top score and the fastest of the 27/27 models, and it stays fully resident
at 32k (17 GB, 100% GPU).
