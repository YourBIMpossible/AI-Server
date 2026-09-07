from pathlib import Path

import pdfplumber

from pickup_checker.models import Matched, UnmatchedA, UnmatchedB, Ambiguous, SheetRef
from pickup_checker.sheets import parse_sheet_number, pair_sheets
from tests.fixtures.pdf_builder import build_simple_pdf


def _open_pages(path: str):
    pdf = pdfplumber.open(path)
    return pdf, pdf.pages


def test_parse_sheet_number_finds_right_edge_title_block(tmp_path: Path):
    pdf_path = tmp_path / "sheet.pdf"
    # page is 8.5in wide; place sheet number at x=7.5in (within right 25% = >=6.375in)
    build_simple_pdf(str(pdf_path), pages=[[("E1.01", 7.5, 1.0), ("floor plan notes", 1.0, 5.0)]])
    pdf, pages = _open_pages(str(pdf_path))
    assert parse_sheet_number(pages[0]) == "E1.01"
    pdf.close()


def test_parse_sheet_number_ignores_body_text_outside_right_strip(tmp_path: Path):
    pdf_path = tmp_path / "sheet2.pdf"
    # "A-101" placed in body text (x=1.0in, well left of the right 25% strip) must NOT match
    build_simple_pdf(str(pdf_path), pages=[[("see A-101 for continuation", 1.0, 5.0)]])
    pdf, pages = _open_pages(str(pdf_path))
    assert parse_sheet_number(pages[0]) is None
    pdf.close()


def test_pair_sheets_matches_identical_numbers(tmp_path: Path):
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E1.01", 7.5, 1.0)]])
    doc_a, pages_a = _open_pages(str(pdf_a))
    doc_b, pages_b = _open_pages(str(pdf_b))

    pairings = pair_sheets(pages_a, pages_b, doc_a_id="a", doc_b_id="b")

    assert len(pairings) == 1
    assert isinstance(pairings[0], Matched)
    assert pairings[0].a.sheet_number == "E1.01"
    assert pairings[0].b.sheet_number == "E1.01"
    doc_a.close()
    doc_b.close()


def test_pair_sheets_reports_unmatched_a_when_sheet_dropped(tmp_path: Path):
    pdf_a = tmp_path / "a2.pdf"
    pdf_b = tmp_path / "b2.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E1.02", 7.5, 1.0)]])
    doc_a, pages_a = _open_pages(str(pdf_a))
    doc_b, pages_b = _open_pages(str(pdf_b))

    pairings = pair_sheets(pages_a, pages_b, doc_a_id="a", doc_b_id="b")

    kinds = {type(p) for p in pairings}
    assert UnmatchedA in kinds
    assert UnmatchedB in kinds
    doc_a.close()
    doc_b.close()
