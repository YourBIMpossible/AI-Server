from pathlib import Path

from reportlab.pdfgen import canvas

from pickup_checker.cli import run_pipeline
from pickup_checker.models import MaxClaim, Verdict
from tests.fixtures.pdf_builder import build_simple_pdf


def test_run_pipeline_mode_2_end_to_end(tmp_path: Path):
    pdf_a = tmp_path / "prior.pdf"
    pdf_b = tmp_path / "revised.pdf"
    build_simple_pdf(str(pdf_a), pages=[[
        ("E1.01", 7.5, 1.0),
        ("NOTE: verify dimension", 1.0, 5.0),
    ]])
    build_simple_pdf(str(pdf_b), pages=[[
        ("E1.01", 7.5, 1.0),
        ("NOTE: dimension verified, revised per RFI 12", 1.0, 5.0),
    ]])
    out_dir = str(tmp_path / "out")

    assessments = run_pipeline(
        prior_marked=None, prior_clean=str(pdf_a), markup_file=None,
        revised=str(pdf_b), out_dir=out_dir,
    )

    assert len(assessments) >= 1
    # Mode 2 can NEVER claim anything about pickups -- enforced structurally.
    assert all(a.max_claim is MaxClaim.REGION_CHANGED for a in assessments)


def test_run_pipeline_mode_2_detects_a_changed_page(tmp_path: Path):
    pdf_a = tmp_path / "p1.pdf"
    pdf_b = tmp_path / "p2.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0), ("ORIGINAL TEXT", 1.0, 5.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E1.01", 7.5, 1.0),
                                            ("COMPLETELY DIFFERENT CONTENT NOW", 1.0, 5.0)]])

    assessments = run_pipeline(
        prior_marked=None, prior_clean=str(pdf_a), markup_file=None,
        revised=str(pdf_b), out_dir=str(tmp_path / "out2"),
    )
    assert len(assessments) == 1
    assert assessments[0].verdict is Verdict.CHANGED


def test_run_pipeline_mode_2_identical_pages_score_unchanged(tmp_path: Path):
    pdf_a = tmp_path / "s1.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0), ("SAME TEXT", 1.0, 5.0)]])

    assessments = run_pipeline(
        prior_marked=None, prior_clean=str(pdf_a), markup_file=None,
        revised=str(pdf_a), out_dir=str(tmp_path / "out3"),
    )
    assert len(assessments) == 1
    assert assessments[0].verdict is Verdict.UNCHANGED


def test_run_pipeline_skips_unmatched_sheets(tmp_path: Path):
    """A sheet present in only one document has nothing to compare, so it
    produces no Assessment -- it is not silently treated as unchanged."""
    pdf_a = tmp_path / "u1.pdf"
    pdf_b = tmp_path / "u2.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E9.99", 7.5, 1.0)]])

    assessments = run_pipeline(
        prior_marked=None, prior_clean=str(pdf_a), markup_file=None,
        revised=str(pdf_b), out_dir=str(tmp_path / "out4"),
    )
    assert assessments == []


def test_run_pipeline_mode_1_anchors_on_annotations(tmp_path: Path):
    """Mode 1 produces one Assessment per markup, not one per page, and its
    max_claim allows markup-status statements."""
    pdf_a = tmp_path / "marked.pdf"
    c = canvas.Canvas(str(pdf_a), pagesize=(612, 792))
    c.drawString(7.5 * 72, 792 - 72, "E1.01")
    c.drawString(72, 792 - (5 * 72), "NOTE: verify dimension")
    c.textAnnotation("fix this", Rect=(72, 792 - (5.2 * 72), 300, 792 - (4.8 * 72)),
                      relative=0)
    c.save()

    pdf_b = tmp_path / "rev.pdf"
    build_simple_pdf(str(pdf_b), pages=[[
        ("E1.01", 7.5, 1.0),
        ("NOTE: verify dimension", 1.0, 5.0),
    ]])

    assessments = run_pipeline(
        prior_marked=str(pdf_a), prior_clean=None, markup_file=None,
        revised=str(pdf_b), out_dir=str(tmp_path / "out5"),
    )
    assert len(assessments) == 1
    assert assessments[0].max_claim is MaxClaim.MARKUP_STATUS_ONLY
