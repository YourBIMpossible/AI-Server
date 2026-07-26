import pytest
from pickup_checker.models import (
    InputMode, MaxClaim, max_claim_for_mode,
    Verdict, Method, MethodParams,
    Region, SheetRef, Matched, UnmatchedA, UnmatchedB, Ambiguous,
    Markup, Evidence, Provenance, Finding, Assessment,
    ReviewStatus, ReviewRecord,
)


def test_max_claim_for_mode_marked_prior_is_markup_status_only():
    assert max_claim_for_mode(InputMode.MARKED_PRIOR) == MaxClaim.MARKUP_STATUS_ONLY


def test_max_claim_for_mode_clean_only_is_region_changed():
    assert max_claim_for_mode(InputMode.CLEAN_ONLY) == MaxClaim.REGION_CHANGED


def test_max_claim_for_mode_separate_markup_is_markup_status_only():
    assert max_claim_for_mode(InputMode.SEPARATE_MARKUP) == MaxClaim.MARKUP_STATUS_ONLY


def test_region_is_frozen_and_holds_canonical_inches():
    r = Region(x0=1.0, y0=2.0, x1=3.0, y1=4.0)
    assert r.x1 - r.x0 == 2.0
    with pytest.raises(Exception):
        r.x0 = 99.0  # frozen dataclass -> raises FrozenInstanceError


def test_sheet_pairing_variants_are_distinct_types():
    a = SheetRef(document_id="docA", page_index=0, sheet_number="E1.01")
    b = SheetRef(document_id="docB", page_index=0, sheet_number="E1.01")
    matched = Matched(a=a, b=b, note=None)
    unmatched = UnmatchedA(a=a)
    ambiguous = Ambiguous(candidates=[(a, b)])
    assert isinstance(matched, Matched)
    assert not isinstance(unmatched, Matched)
    assert not isinstance(ambiguous, Matched)


def test_finding_markup_none_allowed():
    sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
    pairing = Matched(a=sheet, b=sheet, note=None)
    region = Region(x0=0, y0=0, x1=1, y1=1)
    ev = Evidence(text_before="old", text_after="new",
                   pixel_delta_summary=None,
                   crop_before_path="a.png", crop_after_path="b.png")
    prov = Provenance(doc_a_id="d1", doc_b_id="d2", doc_a_page=0, doc_b_page=0,
                       registration_offset=None, registration_confidence=None)
    finding = Finding(
        id="f1", pairing=pairing, markup=None, region=region,
        method=MethodParams(method=Method.TEXT_DIFF, params={}),
        evidence=ev, provenance=prov,
    )
    assert finding.markup is None


def test_review_record_is_mutable():
    from datetime import datetime, timezone
    rec = ReviewRecord(
        finding_id="f1", status=ReviewStatus.PENDING,
        reviewer=None, decision_note=None,
        created_at=datetime.now(timezone.utc), resolved_at=None,
    )
    rec.status = ReviewStatus.CONFIRMED  # must NOT raise -- ReviewRecord is mutable
    assert rec.status == ReviewStatus.CONFIRMED
