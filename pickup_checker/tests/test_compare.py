from pathlib import Path

import pdfplumber

from pickup_checker.compare import normalize_text, compare_region_text
from pickup_checker.models import Matched, Method, Region, SheetRef
from tests.fixtures.pdf_builder import build_simple_pdf


def test_normalize_text_collapses_whitespace():
    assert normalize_text("hello\n  world\t") == "hello world"
    assert normalize_text("  a   b  ") == "a b"


def test_compare_region_text_detects_unchanged_content(tmp_path: Path):
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("NOTE: verify dimension", 1.0, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("NOTE: verify dimension", 1.0, 1.0)]])

    with pdfplumber.open(str(pdf_a)) as doc_a, pdfplumber.open(str(pdf_b)) as doc_b:
        page_a, page_b = doc_a.pages[0], doc_b.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
        pairing = Matched(a=sheet, b=sheet, note=None)
        region = Region(x0=0.5, y0=0.5, x1=6.0, y1=1.5)

        finding = compare_region_text(page_a, page_b, region, pairing, markup=None,
                                        doc_a_id="a", doc_b_id="b")
        assert finding.evidence.text_before is not None
        assert normalize_text(finding.evidence.text_before) == normalize_text(
            finding.evidence.text_after)
        assert finding.method.method is Method.TEXT_DIFF


def test_compare_region_text_detects_changed_content(tmp_path: Path):
    pdf_a = tmp_path / "a2.pdf"
    pdf_b = tmp_path / "b2.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("NOTE: verify dimension", 1.0, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("NOTE: dimension verified OK", 1.0, 1.0)]])

    with pdfplumber.open(str(pdf_a)) as doc_a, pdfplumber.open(str(pdf_b)) as doc_b:
        page_a, page_b = doc_a.pages[0], doc_b.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
        pairing = Matched(a=sheet, b=sheet, note=None)
        region = Region(x0=0.5, y0=0.5, x1=6.0, y1=1.5)

        finding = compare_region_text(page_a, page_b, region, pairing, markup=None,
                                        doc_a_id="a", doc_b_id="b")
        assert normalize_text(finding.evidence.text_before) != normalize_text(
            finding.evidence.text_after)


# --- raster fallback path ---

import pypdfium2 as pdfium

from pickup_checker.compare import compare_region_raster


def test_compare_region_raster_detects_pixel_difference(tmp_path: Path):
    pdf_a = tmp_path / "ra.pdf"
    pdf_b = tmp_path / "rb.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("plain content", 1.0, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("plain content CHANGED HERE", 1.0, 1.0)]])

    doc_a = pdfium.PdfDocument(str(pdf_a))
    doc_b = pdfium.PdfDocument(str(pdf_b))
    sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
    pairing = Matched(a=sheet, b=sheet, note=None)
    region = Region(x0=0.5, y0=0.5, x1=6.0, y1=1.5)
    out_dir = str(tmp_path / "crops")

    finding = compare_region_raster(doc_a[0], doc_b[0], region, pairing, markup=None,
                                      doc_a_id="a", doc_b_id="b", out_dir=out_dir)
    doc_a.close()
    doc_b.close()

    assert finding.evidence.pixel_delta_summary is not None
    assert finding.evidence.pixel_delta_summary["diff_ratio"] > 0.0
    assert Path(finding.evidence.crop_before_path).exists()
    assert Path(finding.evidence.crop_after_path).exists()
    assert finding.method.method is Method.RASTER_DIFF


def test_compare_region_raster_near_zero_diff_for_identical_regions(tmp_path: Path):
    pdf_a = tmp_path / "rc.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("identical", 1.0, 1.0)]])

    doc_a = pdfium.PdfDocument(str(pdf_a))
    doc_b = pdfium.PdfDocument(str(pdf_a))  # same file, same content
    sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
    pairing = Matched(a=sheet, b=sheet, note=None)
    region = Region(x0=0.5, y0=0.5, x1=6.0, y1=1.5)
    out_dir = str(tmp_path / "crops2")

    finding = compare_region_raster(doc_a[0], doc_b[0], region, pairing, markup=None,
                                      doc_a_id="a", doc_b_id="a", out_dir=out_dir)
    doc_a.close()
    doc_b.close()

    assert finding.evidence.pixel_delta_summary["diff_ratio"] < 0.01
