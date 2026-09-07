"""Structural markup extraction from PDF annotation objects. Highest-confidence
tier -- exact coordinates, no image heuristics involved.

pdfplumber's .annots dicts were probed directly (v0.11.10) rather than assumed:
top-level keys include x0/x1/top/bottom (same convention as extract_words()),
'contents' for the comment body, and 'title' for the author (PDF /T). There is
NO top-level 'subtype' key -- Subtype lives in data['Subtype'] -- so nothing here
depends on one. Field presence varies by producer (Bluebeam vs Acrobat), hence
the defensive .get() access.
"""
from __future__ import annotations

import uuid

from pickup_checker.geometry import page_to_canonical
from pickup_checker.models import Markup, SheetRef


def extract_annotation_markups(page, sheet: SheetRef) -> list[Markup]:
    annots = getattr(page, "annots", None) or []
    result: list[Markup] = []
    for a in annots:
        bbox = (a.get("x0"), a.get("top"), a.get("x1"), a.get("bottom"))
        if None in bbox:
            continue  # malformed annotation dict -- skip rather than crash the run
        region = page_to_canonical(page, bbox)
        result.append(Markup(
            id=str(uuid.uuid4()),
            sheet=sheet,
            region=region,
            form="annotation",
            author=a.get("title"),
            comment_text=a.get("contents"),
            source_page_rotation_applied=getattr(page, "rotation", 0) or 0,
        ))
    return result
