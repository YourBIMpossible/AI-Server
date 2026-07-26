from pathlib import Path

from tests.fixtures.pdf_builder import build_simple_pdf, set_page_rotation
import pdfplumber


def test_build_simple_pdf_is_readable(tmp_path: Path):
    pdf_path = tmp_path / "smoke.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("HELLO", 1.0, 1.0)]])

    with pdfplumber.open(str(pdf_path)) as pdf:
        assert len(pdf.pages) == 1
        text = pdf.pages[0].extract_text()
        assert "HELLO" in text


def test_set_page_rotation_round_trips(tmp_path: Path):
    pdf_path = tmp_path / "rotated.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("X", 1.0, 1.0)]])
    set_page_rotation(str(pdf_path), page_index=0, degrees=90)

    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf_path))
    assert doc[0].get_rotation() == 90
    doc.close()
