"""Sheet-number parsing and cross-document pairing. No guessing: ambiguous
matches are reported as Ambiguous, never silently resolved (spec section 7)."""
from __future__ import annotations

import re

from pickup_checker.models import (
    Ambiguous, Matched, SheetPairing, SheetRef, UnmatchedA, UnmatchedB,
)

SHEET_NUMBER_RE = re.compile(r"\b([A-Z]{1,3}[-.]?\d{1,4}(?:\.\d{1,2})?)\b")
RIGHT_STRIP_FRACTION = 0.25  # search only the right-most quarter of the page width


def parse_sheet_number(page) -> str | None:
    """Searches the right-most quarter of the page (any vertical position) for a
    sheet-number-shaped token. Returns the first match found, or None.

    Right-edge-only is deliberate: real ARCH-E1 title blocks sit on the right
    edge at varying vertical positions, and restricting the search prevents body
    text like "see A-101 for continuation" from being read as this sheet's number.
    """
    right_edge_x = page.width * (1.0 - RIGHT_STRIP_FRACTION)
    words = page.extract_words()
    candidates = [w for w in words if w["x0"] >= right_edge_x]
    for w in candidates:
        m = SHEET_NUMBER_RE.fullmatch(w["text"].strip())
        if m:
            return m.group(1)
    return None


def pair_sheets(pages_a, pages_b, doc_a_id: str, doc_b_id: str) -> list[SheetPairing]:
    """Pairs pages across two documents by sheet number.

    Page counts differ between issues in practice (sheets added/dropped) -- that
    is expected, not an error. Unpaired pages surface as UnmatchedA/UnmatchedB
    rather than being silently dropped from the run.
    """
    refs_a = [
        SheetRef(document_id=doc_a_id, page_index=i, sheet_number=parse_sheet_number(p))
        for i, p in enumerate(pages_a)
    ]
    refs_b = [
        SheetRef(document_id=doc_b_id, page_index=i, sheet_number=parse_sheet_number(p))
        for i, p in enumerate(pages_b)
    ]

    by_number_b: dict[str, list[SheetRef]] = {}
    for r in refs_b:
        if r.sheet_number:
            by_number_b.setdefault(r.sheet_number, []).append(r)

    pairings: list[SheetPairing] = []
    used_b_numbers: set[str] = set()

    for ra in refs_a:
        if not ra.sheet_number:
            pairings.append(UnmatchedA(a=ra))
            continue
        candidates = by_number_b.get(ra.sheet_number, [])
        if len(candidates) == 1:
            pairings.append(Matched(a=ra, b=candidates[0], note=None))
            used_b_numbers.add(ra.sheet_number)
        elif len(candidates) == 0:
            pairings.append(UnmatchedA(a=ra))
        else:
            pairings.append(Ambiguous(candidates=[(ra, c) for c in candidates]))

    for number, refs in by_number_b.items():
        if number not in used_b_numbers:
            for r in refs:
                pairings.append(UnmatchedB(b=r))

    # Pages in B with no parseable sheet number are also unmatched -- they were
    # never entered into by_number_b, so report them explicitly here.
    for rb in refs_b:
        if not rb.sheet_number:
            pairings.append(UnmatchedB(b=rb))

    return pairings
