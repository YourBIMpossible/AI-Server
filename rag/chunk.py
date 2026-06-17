"""Heading-aware markdown chunker. Pure and deterministic (identical on Windows/Linux).

A document is split into sections by markdown headings; each section becomes one chunk,
or several size-bounded chunks (with word overlap) if it is long. Every chunk carries the
heading of the section it came from, so retrieval can cite "<file> # <heading>".

Token counts are estimated (~4 chars/token) to avoid a tokenizer dependency.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class Chunk:
    heading: str
    text: str
    ord: int


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _sections(text: str) -> list[tuple[str, str]]:
    """Split into (heading, body) sections. Text before the first heading has heading ''."""
    heading = ""
    buf: list[str] = []
    out: list[tuple[str, str]] = []
    for line in _normalize_newlines(text).split("\n"):
        m = _HEADING.match(line)
        if m:
            if buf:
                out.append((heading, "\n".join(buf).strip()))
                buf = []
            heading = m.group(2).strip()
        else:
            buf.append(line)
    if buf:
        out.append((heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in out if b]


def _split_section(body: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """Split one section body into <=target_tokens pieces with word overlap."""
    if len(body) // _CHARS_PER_TOKEN <= target_tokens:
        return [body]
    words = body.split()
    target_words = max(1, target_tokens * _CHARS_PER_TOKEN)  # rough: ~1 short word/4 chars
    # Approximate words-per-chunk from the average word length so a chunk lands near target.
    avg_len = max(1, sum(len(w) for w in words) // max(1, len(words)) + 1)
    words_per_chunk = max(1, (target_tokens * _CHARS_PER_TOKEN) // avg_len)
    step = max(1, words_per_chunk - overlap_tokens)
    pieces: list[str] = []
    i = 0
    while i < len(words):
        pieces.append(" ".join(words[i : i + words_per_chunk]))
        if i + words_per_chunk >= len(words):
            break
        i += step
    return pieces


def chunk_markdown(
    text: str,
    *,
    target_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """Chunk markdown into heading-tagged, size-bounded pieces with overlap."""
    chunks: list[Chunk] = []
    for heading, body in _sections(text):
        for piece in _split_section(body, target_tokens, overlap_tokens):
            if piece.strip():
                chunks.append(Chunk(heading=heading, text=piece, ord=len(chunks)))
    return chunks
