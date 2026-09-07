"""Canonical coordinate space: physical inches from the top-left of the page AS
VIEWED (post-rotation).

EMPIRICALLY VERIFIED, not assumed (see tests/test_geometry.py's discovery test):
pdfplumber ALREADY corrects for /Rotate. Against a real /Rotate 90 fixture it
reports page.width/height in the rotated orientation (792x612 for a rotated
8.5x11in page) and word coordinates in the rotated viewer frame, with
direction='ttb' and transposed bboxes.

This differs from PyMuPDF, which returns raw unrotated-MediaBox coordinates --
assuming PyMuPDF semantics here would double-apply the rotation and silently
produce wrong crop regions. That exact class of bug (a /Rotate 90 page yielding
zero words from a region that was full of text) is why this module's behavior was
established by running a test rather than by reading documentation.
"""
from __future__ import annotations

POINTS_PER_INCH = 72.0


def page_to_canonical(page, bbox: tuple[float, float, float, float]):
    """Convert a pdfplumber bbox (x0, top, x1, bottom) in points to canonical
    inches. pdfplumber's coordinates are already rotation-corrected, so this is
    a pure unit conversion."""
    from pickup_checker.models import Region

    x0, top, x1, bottom = bbox
    return Region(
        x0=x0 / POINTS_PER_INCH,
        y0=top / POINTS_PER_INCH,
        x1=x1 / POINTS_PER_INCH,
        y1=bottom / POINTS_PER_INCH,
    )
