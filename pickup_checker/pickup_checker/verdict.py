"""PURE scoring: Finding -> Assessment. No PDF library import, no file I/O.

difflib (stdlib) is used for text similarity -- it is not a PDF library and does
not violate this module's purity constraint. Purity is what lets the golden-set
gate harness run against fixtures with zero PDF parsing, and it is enforced by a
test (test_verdict_module_imports_no_pdf_library), not just by convention.

FAIL TOWARD REVIEW: any comparison with unresolved uncertainty resolves to
INDETERMINATE, which stays visible in the queue. Uncertainty never resolves
toward CHANGED, because CHANGED sorts last and would remove the item from view.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from pickup_checker.models import (
    Assessment, Finding, InputMode, Method, Verdict, max_claim_for_mode,
)

_WHITESPACE_RE = re.compile(r"\s+")

# Suspicion ranks the queue; it never bypasses review. UNCHANGED is the target
# signal (an unaddressed markup), so it outranks everything else.
SUSPICION_UNCHANGED = 0.95
SUSPICION_INDETERMINATE = 0.50
SUSPICION_CHANGED = 0.20

# Evidence quality is a SEPARATE axis from suspicion: how much to trust the
# observation itself, independent of how alarming it is.
QUALITY_TEXT = 0.95     # primary path: exact character comparison
QUALITY_RASTER = 0.60   # fallback: pixel heuristic
QUALITY_NO_DATA = 0.20  # nothing to compare


def _normalize(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", s).strip()


def score_finding(
    finding: Finding,
    run_mode: InputMode,
    text_similarity_threshold: float = 0.90,
    pixel_diff_threshold: float = 0.05,
) -> Assessment:
    max_claim = max_claim_for_mode(run_mode)
    ev = finding.evidence

    if finding.method.method is Method.RASTER_DIFF:
        summary = ev.pixel_delta_summary
        if summary is None:
            return Assessment(
                finding_id=finding.id, verdict=Verdict.INDETERMINATE,
                suspicion_score=SUSPICION_INDETERMINATE,
                evidence_quality=QUALITY_NO_DATA, max_claim=max_claim,
            )
        if summary["diff_ratio"] >= pixel_diff_threshold:
            verdict, suspicion = Verdict.CHANGED, SUSPICION_CHANGED
        else:
            verdict, suspicion = Verdict.UNCHANGED, SUSPICION_UNCHANGED
        return Assessment(
            finding_id=finding.id, verdict=verdict, suspicion_score=suspicion,
            evidence_quality=QUALITY_RASTER, max_claim=max_claim,
        )

    # TEXT_DIFF / ANNOTATION_STRUCTURAL: compare normalized text
    if ev.text_before is None or ev.text_after is None:
        return Assessment(
            finding_id=finding.id, verdict=Verdict.INDETERMINATE,
            suspicion_score=SUSPICION_INDETERMINATE,
            evidence_quality=QUALITY_NO_DATA, max_claim=max_claim,
        )

    before = _normalize(ev.text_before)
    after = _normalize(ev.text_after)
    similarity = SequenceMatcher(None, before, after).ratio()

    if similarity >= text_similarity_threshold:
        verdict, suspicion = Verdict.UNCHANGED, SUSPICION_UNCHANGED
    else:
        verdict, suspicion = Verdict.CHANGED, SUSPICION_CHANGED

    return Assessment(
        finding_id=finding.id, verdict=verdict, suspicion_score=suspicion,
        evidence_quality=QUALITY_TEXT, max_claim=max_claim,
    )
