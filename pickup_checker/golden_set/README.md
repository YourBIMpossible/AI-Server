# GoldenSet v1.0 — labeling protocol

Full context: `docs/superpowers/specs/2026-07-25-pdf-pickup-checker-design.md`, section 11.

## Composition target

**6 jobs**, spanning all three input modes (marked-prior, clean-only, separate-markup) and
all three markup forms (annotation, flattened, scanned), with >=15 markup instances per form
across the set. Sized to cover the failure modes, not padded — grow only once v1.0 stops
discriminating between good and bad runs.

## Directory shape (per job)

    golden_set/
      job-01-<short-name>/
        prior.pdf              (or prior_marked.pdf / prior_clean.pdf, per that job's mode)
        markup.pdf             (only if that job is separate-markup mode)
        revised.pdf
        labels.json            (schema below)

## Labeling rules (FROZEN — do not adjust without updating the spec)

- Ground truth per region is **binary**: `CHANGED` or `UNCHANGED`. `INDETERMINATE` is a tool
  OUTPUT only — never assign it as a label. It is scored as an abstain: it raises review
  load but is never counted wrong.
- **Revision clouds and revision-block tags are excluded from content comparison.** A cloud
  drawn around an otherwise-untouched region is labeled `UNCHANGED`. Without this rule every
  picked-up sheet trivially self-certifies as changed via its own revision cloud.
- Text reflow with identical content -> `UNCHANGED`.
- Line weight / color / hatch change only, no content change -> `CHANGED`.
- Content deleted (not replaced) -> `CHANGED`.
- Residual sub-tolerance shift after registration -> `UNCHANGED`.
- **One markup = one reviewer intent.** A cloud with an attached callout is one markup, not
  two. Loose ink scribbles within one bounding box and one apparent gesture are one markup.
- Sheet matching: same sheet number + same discipline = matched. A renumbered/resheeted
  sheet is labeled matched with an explicit `note` explaining the renumber, so the matcher
  isn't penalized for a real-world renumber it had no way to detect from content alone.

## Anti-anchoring rule

Labels **start from the tool's own proposals** as a labeling aid, but the labeler must be
free to **fully overwrite** a proposal, not merely edit it. Treat every proposed label as
disposable.

Anchoring on the tool's own output during golden-set creation biases ground truth toward
whatever the tool already believes, which defeats the entire point of an independent gate.
If a proposal looks right, confirm it because you checked the drawing — not because it was
already filled in.

## labels.json schema

    {
      "job_id": "job-01-example",
      "input_mode": "marked_prior",
      "regions": [
        {
          "sheet_number": "E1.01",
          "markup_form": "annotation",
          "ground_truth": "UNCHANGED",
          "note": null
        }
      ]
    }

`input_mode` is one of `marked_prior` | `clean_only` | `separate_markup`.
`markup_form` is one of `annotation` | `flattened` | `scanned`.
`ground_truth` is one of `CHANGED` | `UNCHANGED` — never `INDETERMINATE`.

## Gate thresholds

Frozen in `pickup_checker/gates.py`, copied verbatim from spec section 11. **They freeze
before the first real run against this set.** Adjusting a threshold after seeing results is
moving the goalposts.

Scanned-form markup extraction is EXPECTED to fail its gate at v1.0. That is the correct
outcome — it means scanned input is not yet trusted, not that the gate is miscalibrated.

## Status

No real golden-set jobs exist yet — this is manual work to do when ready. Run
`python run_golden_eval.py` at any time; until real jobs are added it reports a synthetic
demo set (which deliberately FAILs, proving the gate measures rather than flatters).

Real-job evaluation — loading `labels.json`, running the pipeline per job, and computing the
sheet-matching, markup-extraction and queue-usefulness metrics — is not yet wired. Only the
region-comparison metric path exists today.
