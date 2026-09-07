"""Flattened (burned-in) markup detection via a color-saturation heuristic on a
rasterized page. Medium confidence tier. No OpenCV/SciPy -- clustering is a
simple grid flood-fill in numpy."""
from __future__ import annotations

import uuid

import numpy as np

from pickup_checker.models import Markup, Region, SheetRef

POINTS_PER_INCH = 72.0
SATURATION_THRESHOLD = 60  # max(R,G,B) - min(R,G,B); grayscale/black text is ~0
GRID_CELL_PX = 20          # coarse clustering cell size -- tuned for markup-scale
                            # regions (inches), not pixel-scale noise


def _saturated_mask(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.int16)
    channel_max = rgb.max(axis=-1)
    channel_min = rgb.min(axis=-1)
    return (channel_max - channel_min) >= SATURATION_THRESHOLD


def _cluster_grid_cells(mask: np.ndarray, cell_px: int) -> list[tuple[int, int, int, int]]:
    """Coarse clustering: mark grid cells containing >=1 flagged pixel, merge
    adjacent marked cells into rectangular bounding boxes via simple
    4-connectivity flood fill. Sufficient for cloud-sized markups; not a general
    computer-vision algorithm."""
    h, w = mask.shape
    rows = (h + cell_px - 1) // cell_px
    cols = (w + cell_px - 1) // cell_px
    grid = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for c in range(cols):
            cell = mask[r * cell_px:(r + 1) * cell_px, c * cell_px:(c + 1) * cell_px]
            grid[r, c] = bool(cell.any())

    visited = np.zeros_like(grid)
    boxes: list[tuple[int, int, int, int]] = []
    for r in range(rows):
        for c in range(cols):
            if grid[r, c] and not visited[r, c]:
                stack = [(r, c)]
                visited[r, c] = True
                min_r = max_r = r
                min_c = max_c = c
                while stack:
                    cr, cc = stack.pop()
                    min_r, max_r = min(min_r, cr), max(max_r, cr)
                    min_c, max_c = min(min_c, cc), max(max_c, cc)
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = cr + dr, cc + dc
                        if (0 <= nr < rows and 0 <= nc < cols
                                and grid[nr, nc] and not visited[nr, nc]):
                            visited[nr, nc] = True
                            stack.append((nr, nc))
                boxes.append((
                    min_c * cell_px, min_r * cell_px,
                    min((max_c + 1) * cell_px, w), min((max_r + 1) * cell_px, h),
                ))
    return boxes


def extract_flattened_markups(page, sheet: SheetRef, dpi: int = 150) -> list[Markup]:
    """`page` is a pypdfium2 page (rendering is required), NOT a pdfplumber page."""
    scale = dpi / POINTS_PER_INCH
    bitmap = page.render(scale=scale, rotation=0)
    pil_image = bitmap.to_pil().convert("RGB")
    rgb = np.array(pil_image)

    mask = _saturated_mask(rgb)
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
            id=str(uuid.uuid4()), sheet=sheet, region=region, form="flattened",
            author=None, comment_text=None,
            source_page_rotation_applied=page.get_rotation(),
        ))
    return result
