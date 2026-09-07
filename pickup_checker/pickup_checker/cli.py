"""Wires ingest -> sheets -> markups -> compare -> verdict into one pipeline.

Mode-specific behavior:
  MARKED_PRIOR / SEPARATE_MARKUP -- anchor on extracted markups, one Finding per
    markup region. This is the real product: the markup is the query.
  CLEAN_ONLY -- no markup source exists, so there is nothing to anchor on. Falls
    back to comparing whole matched pages, which is exactly the spec's stated
    ceiling for this mode: "region changed", at page granularity, never a
    statement about pickups.

MILESTONE 1 SCOPE -- annotation-form markups only. extract_flattened_markups and
extract_scanned_markups take a pypdfium2 page (rendering is required), while
extract_annotation_markups takes a pdfplumber page. Running all three from one
pipeline means holding both representations of every sheet open simultaneously.
That is real wiring work, not a one-liner, and it is deferred rather than
half-built: annotation is the highest-confidence tier (gate: recall 0.99) and is
sufficient to prove the pipeline end-to-end. The flattened/scanned extractors are
implemented and independently tested -- only their CLI wiring is pending.
"""
from __future__ import annotations

import argparse
import sys

from pickup_checker.compare import compare_region_text
from pickup_checker.ingest import load_documents
from pickup_checker.markups.annotations import extract_annotation_markups
from pickup_checker.models import Assessment, InputMode, Matched, Region
from pickup_checker.sheets import pair_sheets
from pickup_checker.verdict import score_finding

POINTS_PER_INCH = 72.0


def run_pipeline(
    prior_marked: str | None,
    prior_clean: str | None,
    markup_file: str | None,
    revised: str,
    out_dir: str,
) -> list[Assessment]:
    doc_set = load_documents(prior_marked, prior_clean, markup_file, revised)
    try:
        pairings = pair_sheets(
            doc_set.prior.pages, doc_set.revised.pages,
            doc_a_id=doc_set.prior_id, doc_b_id=doc_set.revised_id,
        )

        assessments: list[Assessment] = []
        for pairing in pairings:
            # Unmatched/ambiguous sheets have nothing to compare against, so they
            # produce no Finding. They surface to the reviewer as their own
            # run-level outcome rather than as a Finding with missing data.
            if not isinstance(pairing, Matched):
                continue

            page_a = doc_set.prior.pages[pairing.a.page_index]
            page_b = doc_set.revised.pages[pairing.b.page_index]

            if doc_set.mode is InputMode.CLEAN_ONLY:
                region = Region(
                    x0=0.0, y0=0.0,
                    x1=page_a.width / POINTS_PER_INCH,
                    y1=page_a.height / POINTS_PER_INCH,
                )
                finding = compare_region_text(
                    page_a, page_b, region, pairing, markup=None,
                    doc_a_id=doc_set.prior_id, doc_b_id=doc_set.revised_id,
                )
                assessments.append(score_finding(finding, run_mode=doc_set.mode))
                continue

            # MARKED_PRIOR: markups live on the prior page.
            # SEPARATE_MARKUP: markups live in their own document.
            if doc_set.mode is InputMode.SEPARATE_MARKUP and doc_set.markup is not None:
                markup_source_page = doc_set.markup.pages[pairing.a.page_index]
            else:
                markup_source_page = page_a

            markups = extract_annotation_markups(markup_source_page, pairing.a)
            for markup in markups:
                finding = compare_region_text(
                    page_a, page_b, markup.region, pairing, markup=markup,
                    doc_a_id=doc_set.prior_id, doc_b_id=doc_set.revised_id,
                )
                assessments.append(score_finding(finding, run_mode=doc_set.mode))

        return assessments
    finally:
        doc_set.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF pickup checker (detection core)")
    parser.add_argument("--prior-marked", help="prior issue WITH markups on it (mode 1)")
    parser.add_argument("--prior-clean", help="clean prior issue (mode 2/3)")
    parser.add_argument("--markup-file", help="separate markup document (mode 3)")
    parser.add_argument("--revised", required=True, help="the new issue to check")
    parser.add_argument("--out-dir", default="./out")
    args = parser.parse_args()

    assessments = run_pipeline(
        prior_marked=args.prior_marked, prior_clean=args.prior_clean,
        markup_file=args.markup_file, revised=args.revised, out_dir=args.out_dir,
    )

    # Queue order: UNCHANGED first (the target signal -- an unaddressed markup),
    # then INDETERMINATE, then by suspicion and evidence quality.
    order = {"unchanged": 0, "indeterminate": 1, "changed": 2}
    ranked = sorted(
        assessments,
        key=lambda a: (order[a.verdict.value], -a.suspicion_score, -a.evidence_quality),
    )
    for a in ranked:
        print(f"{a.finding_id}  {a.verdict.value:13s}  suspicion={a.suspicion_score:.2f}  "
              f"quality={a.evidence_quality:.2f}  max_claim={a.max_claim.value}")
    if not ranked:
        print("no comparable regions found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
