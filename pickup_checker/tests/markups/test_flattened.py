from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

from pickup_checker.markups.flattened import extract_flattened_markups
from pickup_checker.models import SheetRef


def _build_pdf_with_red_square(path: str) -> None:
    """Plain reportlab canvas with a red-filled rectangle -- simulates a flattened
    (burned-in) colored markup with no annotation object behind it."""
    c = canvas.Canvas(path, pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "drawing content")
    c.setFillColorRGB(1.0, 0.0, 0.0)  # saturated red -- the "markup"
    c.rect(72 * 3, 72 * 3, 72, 72, fill=1, stroke=0)
    c.save()


def test_extract_flattened_markups_finds_the_red_square(tmp_path: Path):
    pdf_path = tmp_path / "flat.pdf"
    _build_pdf_with_red_square(str(pdf_path))

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)

    markups = extract_flattened_markups(page, sheet, dpi=100)
    doc.close()

    assert len(markups) == 1
    m = markups[0]
    assert m.form == "flattened"
    # rect drawn at x=3in..4in, y=3in..4in from BOTTOM -> 7in..8in from TOP
    assert 2.7 < m.region.x0 < 3.3
    assert 6.7 < m.region.y0 < 7.3


def test_extract_flattened_markups_returns_empty_for_grayscale_only_page(tmp_path: Path):
    pdf_path = tmp_path / "gray.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "plain black text, no color")
    c.save()

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
    markups = extract_flattened_markups(page, sheet, dpi=100)
    doc.close()
    assert markups == []
