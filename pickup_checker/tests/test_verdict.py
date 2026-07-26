from pickup_checker.models import (
    Evidence, Finding, InputMode, MaxClaim, Matched, Method, MethodParams,
    Provenance, Region, SheetRef, Verdict,
)
from pickup_checker.verdict import score_finding


def _make_finding(text_before, text_after, pixel_delta_summary=None,
                    method=Method.TEXT_DIFF):
    sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
    pairing = Matched(a=sheet, b=sheet, note=None)
    region = Region(x0=0, y0=0, x1=1, y1=1)
    evidence = Evidence(
        text_before=text_before, text_after=text_after,
        pixel_delta_summary=pixel_delta_summary,
        crop_before_path="b.png", crop_after_path="a.png",
    )
    provenance = Provenance(doc_a_id="a", doc_b_id="b", doc_a_page=0, doc_b_page=0,
                              registration_offset=None, registration_confidence=None)
    return Finding(id="f1", pairing=pairing, markup=None, region=region,
                    method=MethodParams(method=method, params={}),
                    evidence=evidence, provenance=provenance)


def test_identical_text_scores_unchanged():
    finding = _make_finding("verify dimension", "verify   dimension")  # whitespace-only
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.UNCHANGED


def test_different_text_scores_changed():
    finding = _make_finding("verify dimension", "dimension verified OK")
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.CHANGED


def test_missing_text_with_no_pixel_data_scores_indeterminate():
    finding = _make_finding(None, None, pixel_delta_summary=None)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.INDETERMINATE


def test_raster_diff_ratio_above_threshold_scores_changed():
    finding = _make_finding(None, None,
                              pixel_delta_summary={"diff_ratio": 0.30, "width": 10,
                                                     "height": 10},
                              method=Method.RASTER_DIFF)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.CHANGED


def test_raster_diff_ratio_below_threshold_scores_unchanged():
    finding = _make_finding(None, None,
                              pixel_delta_summary={"diff_ratio": 0.001, "width": 10,
                                                     "height": 10},
                              method=Method.RASTER_DIFF)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.UNCHANGED


def test_raster_method_with_no_pixel_summary_scores_indeterminate():
    finding = _make_finding(None, None, pixel_delta_summary=None,
                              method=Method.RASTER_DIFF)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.INDETERMINATE


def test_max_claim_matches_run_mode_clean_only():
    finding = _make_finding("a", "b")
    assessment = score_finding(finding, run_mode=InputMode.CLEAN_ONLY)
    assert assessment.max_claim is MaxClaim.REGION_CHANGED


def test_max_claim_matches_run_mode_marked_prior():
    finding = _make_finding("a", "b")
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.max_claim is MaxClaim.MARKUP_STATUS_ONLY


def test_unchanged_verdict_has_high_suspicion():
    """UNCHANGED in a markup region is the target signal -- it must outrank
    CHANGED so it sorts to the top of the review queue."""
    unchanged = score_finding(_make_finding("same", "same"),
                                run_mode=InputMode.MARKED_PRIOR)
    changed = score_finding(_make_finding("old", "brand new text entirely"),
                              run_mode=InputMode.MARKED_PRIOR)
    assert unchanged.suspicion_score > changed.suspicion_score


def test_verdict_module_imports_no_pdf_library():
    """verdict.py must stay pure so the gate harness runs with zero PDF parsing.
    Guards the Global Constraint directly rather than trusting review."""
    import inspect
    import pickup_checker.verdict as v

    source = inspect.getsource(v)
    for banned in ("import pdfplumber", "import pypdfium2", "import reportlab",
                    "import numpy", "from pdfplumber", "from pypdfium2",
                    "from reportlab", "from numpy"):
        assert banned not in source, f"verdict.py must not contain '{banned}'"
