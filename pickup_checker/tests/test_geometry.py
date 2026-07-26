from pathlib import Path

import pdfplumber

from tests.fixtures.pdf_builder import build_simple_pdf, set_page_rotation


def test_discover_pdfplumber_rotation_behavior(tmp_path: Path):
    """Places one word at a known unrotated position, rotates the page 90 degrees,
    and prints/asserts what pdfplumber actually reports. This is the ground truth
    that page_to_canonical() must be implemented against -- not a guess."""
    pdf_path = tmp_path / "rot.pdf"
    # page is 8.5x11in; place a word 1in from left, 1in from top, unrotated
    build_simple_pdf(str(pdf_path), pages=[[("MARK", 1.0, 1.0)]],
                      page_size_inches=(8.5, 11.0))
    set_page_rotation(str(pdf_path), page_index=0, degrees=90)

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        print("page.rotation:", getattr(page, "rotation", "NO ATTR"))
        print("page.width:", page.width, "page.height:", page.height)
        words = page.extract_words()
        print("words:", words)
        assert len(words) == 1  # sanity: the word must still be findable at all

        # Locked-in findings from the first run of this test. If pdfplumber ever
        # changes its rotation handling, these fail loudly instead of silently
        # corrupting every downstream crop region.
        assert page.rotation == 90
        assert (page.width, page.height) == (792, 612), \
            "pdfplumber should report ROTATED page dimensions"
        w = words[0]
        assert w["direction"] == "ttb", "rotated text should read top-to-bottom"
        assert w["x0"] > 700, \
            "a word 1in from the unrotated top-left must land near the rotated top-RIGHT"
        assert w["top"] == 72.0


from pickup_checker.geometry import page_to_canonical


def test_page_to_canonical_unrotated_matches_known_placement(tmp_path: Path):
    pdf_path = tmp_path / "flat.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("MARK", 1.0, 1.0)]],
                      page_size_inches=(8.5, 11.0))
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        word = page.extract_words()[0]
        bbox = (word["x0"], word["top"], word["x1"], word["bottom"])
        region = page_to_canonical(page, bbox)
        # The word was drawn at x=1.0in with its BASELINE at y=1.0in. drawString
        # anchors the baseline, not the bbox top, so the bbox straddles y=1.0:
        # top is above it (ascender), bottom below it (descender).
        assert 0.9 < region.x0 < 1.3
        assert region.y0 < 1.0 < region.y1, \
            f"baseline y=1.0in should fall inside the bbox, got {region.y0}..{region.y1}"


def test_page_to_canonical_rotated_90_stays_within_page_bounds(tmp_path: Path):
    pdf_path = tmp_path / "rot2.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("MARK", 1.0, 1.0)]],
                      page_size_inches=(8.5, 11.0))
    set_page_rotation(str(pdf_path), page_index=0, degrees=90)
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        assert len(words) == 1
        word = words[0]
        bbox = (word["x0"], word["top"], word["x1"], word["bottom"])
        region = page_to_canonical(page, bbox)
        # Must land inside the ROTATED page bounds (11in wide x 8.5in tall).
        # Catches a transform that produces negative/huge coords -- exactly how
        # the original /Rotate bug manifested (crop region outside the real page,
        # yielding zero extracted words).
        assert 0 <= region.x0 <= 11.0
        assert 0 <= region.y0 <= 8.5
        assert region.x1 > region.x0
        assert region.y1 > region.y0
