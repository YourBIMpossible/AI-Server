from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

from pickup_checker.markups.scanned import extract_scanned_markups
from pickup_checker.models import SheetRef


def _build_pdf_with_faint_blue_ink(path: str) -> None:
    """Simulates a scanned pen markup: duller/less saturated than a digital
    markup color, placed over plain content."""
    c = canvas.Canvas(path, pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "scanned drawing content")
    c.setFillColorRGB(0.3, 0.3, 0.75)  # duller blue, ballpoint-pen-ish
    c.rect(72 * 2, 72 * 2, 72, 72, fill=1, stroke=0)
    c.save()


def test_extract_scanned_markups_finds_the_faint_ink(tmp_path: Path):
    pdf_path = tmp_path / "scan.pdf"
    _build_pdf_with_faint_blue_ink(str(pdf_path))

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)

    markups = extract_scanned_markups(page, sheet, dpi=100)
    doc.close()

    assert len(markups) == 1
    assert markups[0].form == "scanned"


def test_extract_scanned_markups_returns_empty_for_grayscale_only_page(tmp_path: Path):
    pdf_path = tmp_path / "gray_scan.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "no ink here, just black text")
    c.save()

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
    markups = extract_scanned_markups(page, sheet, dpi=100)
    doc.close()
    assert markups == []
