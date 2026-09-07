"""Scanned-markup detection: colored-ink heuristic, no deskew. Low confidence
tier BY DESIGN -- the spec explicitly expects this path to fail its v1.0 gate
(recall_min 0.70 vs annotation's 0.99), so effort here is deliberately minimal
rather than a full CV pipeline. Building deskew now would be work spent on a
path already predicted not to ship trusted."""
from __future__ import annotations

import uuid

import numpy as np

from pickup_checker.markups.flattened import GRID_CELL_PX, _cluster_grid_cells
from pickup_checker.models import Markup, Region, SheetRef

POINTS_PER_INCH = 72.0
SCANNED_SATURATION_THRESHOLD = 30  # lower than flattened's 60 -- scanned ink is duller


def extract_scanned_markups(page, sheet: SheetRef, dpi: int = 150) -> list[Markup]:
    """`page` is a pypdfium2 page (rendering is required), NOT a pdfplumber page."""
    scale = dpi / POINTS_PER_INCH
    bitmap = page.render(scale=scale, rotation=0)
    pil_image = bitmap.to_pil().convert("RGB")
    rgb = np.array(pil_image).astype(np.int16)

    channel_max = rgb.max(axis=-1)
    channel_min = rgb.min(axis=-1)
    mask = (channel_max - channel_min) >= SCANNED_SATURATION_THRESHOLD
    if not mask.any():
        return []

    px_per_inch = float(dpi)
    boxes_px = _cluster_grid_cells(mask, GRID_CELL_PX)
    result: list[Markup] = []
    for x0_px, y0_px, x1_px, y1_px in boxes_px:
        region = Region(
            x0=x0_px / px_per_inch, y0=y0_px / px_per_inch,
            x1=x1_px / px_per_inch, y1=y1_px / px_per_inch,
        )
        result.append(Markup(
            id=str(uuid.uuid4()), sheet=sheet, region=region, form="scanned",
            author=None, comment_text=None,
            source_page_rotation_applied=page.get_rotation(),
        ))
    return result
