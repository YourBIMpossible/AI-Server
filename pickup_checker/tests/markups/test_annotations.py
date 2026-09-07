from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas

from pickup_checker.markups.annotations import extract_annotation_markups
from pickup_checker.models import SheetRef
from tests.fixtures.pdf_builder import build_simple_pdf


def _build_pdf_with_real_annotation(path: str) -> None:
    """Uses reportlab's textAnnotation to emit a GENUINE PDF annotation object,
    so this tests the real pdfplumber .annots shape rather than a mock of it.

    Verified structure (probed against pdfplumber 0.11.10): top-level keys are
    x0/x1/top/bottom/contents/title/data/... -- note there is NO top-level
    'subtype' key; Subtype lives inside data['Subtype'].
    """
    c = canvas.Canvas(path, pagesize=(612, 792))  # 8.5x11in
    c.drawString(72, 720, "drawing content")
    # Rect is in PDF bottom-left-origin points: x0=72, y0=648, x1=144, y1=720
    c.textAnnotation("check this dimension", Rect=(72, 648, 144, 720), relative=0)
    c.save()


def test_extract_annotation_markups_returns_empty_list_when_no_annotations(tmp_path: Path):
    pdf_path = tmp_path / "plain.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("hello", 1.0, 1.0)]])
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
        markups = extract_annotation_markups(page, sheet)
        assert markups == []


def test_extract_annotation_markups_maps_a_real_annotation(tmp_path: Path):
    pdf_path = tmp_path / "annotated.pdf"
    _build_pdf_with_real_annotation(str(pdf_path))

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number="E1.01")
        markups = extract_annotation_markups(page, sheet)

        assert len(markups) == 1
        m = markups[0]
        assert m.form == "annotation"
        assert m.comment_text == "check this dimension"
        assert m.sheet.sheet_number == "E1.01"
        # Rect y-range 648..720 in bottom-up points on a 792pt-tall page
        # -> top=72pt=1.0in, bottom=144pt=2.0in in canonical top-down inches
        assert m.region.x0 == 1.0
        assert m.region.x1 == 2.0
        assert m.region.y0 == 1.0
        assert m.region.y1 == 2.0


def test_extract_annotation_markups_reads_author_from_title_field(tmp_path: Path, monkeypatch):
    """PDF stores the annotation author in /T, surfaced by pdfplumber as 'title'.
    reportlab's textAnnotation doesn't set /T, so this maps the field directly."""
    pdf_path = tmp_path / "plain2.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("hello", 1.0, 1.0)]])
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
        fake = {"x0": 72.0, "x1": 144.0, "top": 72.0, "bottom": 144.0,
                 "contents": "note", "title": "J.SMITH"}
        monkeypatch.setattr(type(page), "annots", property(lambda self: [fake]))
        markups = extract_annotation_markups(page, sheet)
        assert markups[0].author == "J.SMITH"


def test_extract_annotation_markups_skips_malformed_annotation(tmp_path: Path, monkeypatch):
    """A producer-specific annotation missing coordinates must be skipped, not
    crash the whole run."""
    pdf_path = tmp_path / "plain3.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("hello", 1.0, 1.0)]])
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
        good = {"x0": 72.0, "x1": 144.0, "top": 72.0, "bottom": 144.0,
                 "contents": "ok", "title": None}
        malformed = {"contents": "no coords here", "title": None}
        monkeypatch.setattr(type(page), "annots", property(lambda self: [malformed, good]))
        markups = extract_annotation_markups(page, sheet)
        assert len(markups) == 1
        assert markups[0].comment_text == "ok"
