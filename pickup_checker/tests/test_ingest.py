from pathlib import Path

import pytest

from pickup_checker.models import InputMode
from pickup_checker.ingest import detect_input_mode, load_documents
from tests.fixtures.pdf_builder import build_simple_pdf


def test_detect_mode_1_marked_prior():
    mode = detect_input_mode(prior_marked="a.pdf", prior_clean=None,
                               markup_file=None, revised="b.pdf")
    assert mode is InputMode.MARKED_PRIOR


def test_detect_mode_2_clean_only():
    mode = detect_input_mode(prior_marked=None, prior_clean="a.pdf",
                               markup_file=None, revised="b.pdf")
    assert mode is InputMode.CLEAN_ONLY


def test_detect_mode_3_separate_markup():
    mode = detect_input_mode(prior_marked=None, prior_clean="a.pdf",
                               markup_file="markup.pdf", revised="b.pdf")
    assert mode is InputMode.SEPARATE_MARKUP


def test_detect_mode_rejects_no_prior_at_all():
    with pytest.raises(ValueError, match="prior"):
        detect_input_mode(prior_marked=None, prior_clean=None,
                            markup_file=None, revised="b.pdf")


def test_detect_mode_rejects_both_prior_kinds():
    with pytest.raises(ValueError, match="not both"):
        detect_input_mode(prior_marked="a.pdf", prior_clean="c.pdf",
                            markup_file=None, revised="b.pdf")


def test_load_documents_mode_2(tmp_path: Path):
    pdf_a = tmp_path / "prior.pdf"
    pdf_b = tmp_path / "revised.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E1.01", 7.5, 1.0)]])

    doc_set = load_documents(prior_marked=None, prior_clean=str(pdf_a),
                               markup_file=None, revised=str(pdf_b))
    try:
        assert doc_set.mode is InputMode.CLEAN_ONLY
        assert len(doc_set.prior.pages) == 1
        assert len(doc_set.revised.pages) == 1
        assert doc_set.markup is None
    finally:
        doc_set.close()
