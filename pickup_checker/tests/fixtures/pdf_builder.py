"""Generates small synthetic PDFs for tests. No PDF library imported here is a
production dependency of pickup_checker itself beyond what's already approved
(reportlab for authoring, pypdfium2 for rotation) -- this module is test-only."""
from __future__ import annotations

import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

POINTS_PER_INCH = 72.0


def build_simple_pdf(
    path: str,
    pages: list[list[tuple[str, float, float]]],
    page_size_inches: tuple[float, float] = (8.5, 11.0),
) -> None:
    """Each page is a list of (text, x_inches, y_inches) placements. Origin is
    TOP-LEFT in inches (matches pickup_checker's canonical space) -- this function
    does the flip to reportlab's bottom-left-origin coordinate system internally."""
    width_pt = page_size_inches[0] * POINTS_PER_INCH
    height_pt = page_size_inches[1] * POINTS_PER_INCH
    c = canvas.Canvas(path, pagesize=(width_pt, height_pt))
    for page_items in pages:
        for text, x_in, y_in in page_items:
            x_pt = x_in * POINTS_PER_INCH
            y_pt = height_pt - (y_in * POINTS_PER_INCH)  # flip to bottom-left origin
            c.drawString(x_pt, y_pt, text)
        c.showPage()
    c.save()


def set_page_rotation(path: str, page_index: int, degrees: int) -> None:
    """Sets the real /Rotate page attribute in place (0/90/180/270), using
    pypdfium2 -- reportlab's canvas.rotate() only rotates drawn CONTENT, not the
    page dictionary's /Rotate entry, so it cannot produce this fixture."""
    doc = pdfium.PdfDocument(path)
    page = doc[page_index]
    page.set_rotation(degrees)
    doc.save(path)
    doc.close()
