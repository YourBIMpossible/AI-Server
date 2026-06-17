"""WP-B chunker: heading-aware, size-bounded, with overlap. Pure + portable (no I/O)."""
from rag.chunk import Chunk, chunk_markdown


def test_one_chunk_per_small_section_tagged_with_its_heading():
    text = (
        "# Title\n\nintro para\n\n"
        "## Section A\n\nalpha beta gamma\n\n"
        "## Section B\n\ndelta\n"
    )
    chunks = chunk_markdown(text)
    assert [c.heading for c in chunks] == ["Title", "Section A", "Section B"]
    by_heading = {c.heading: c.text for c in chunks}
    assert "intro para" in by_heading["Title"]
    assert "alpha beta gamma" in by_heading["Section A"]
    assert "delta" in by_heading["Section B"]
    assert [c.ord for c in chunks] == [0, 1, 2]


def test_preamble_before_first_heading_is_kept():
    chunks = chunk_markdown("loose preamble text\n\n# H\n\nbody\n")
    assert chunks[0].heading == ""
    assert "loose preamble text" in chunks[0].text


def test_large_section_splits_into_multiple_chunks_with_overlap():
    body = " ".join(f"w{i}" for i in range(2000))
    chunks = chunk_markdown(f"# Big\n\n{body}\n", target_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1
    assert all(c.heading == "Big" for c in chunks)
    assert all(isinstance(c, Chunk) for c in chunks)
    # consecutive chunks overlap: the tail of chunk N reappears at the head of chunk N+1
    tail = set(chunks[0].text.split()[-5:])
    head = set(chunks[1].text.split()[:25])
    assert tail & head


def test_empty_or_whitespace_text_yields_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  \n") == []


def test_crlf_and_lf_chunk_identically():
    lf = "# H\n\nalpha beta\n"
    crlf = "# H\r\n\r\nalpha beta\r\n"
    assert [(c.heading, c.text) for c in chunk_markdown(lf)] == [
        (c.heading, c.text) for c in chunk_markdown(crlf)
    ]
