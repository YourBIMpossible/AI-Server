"""Region comparison. Text-first (primary) and raster (fallback). Produces
Finding objects only -- Verdict/scoring is verdict.py's job, not this module's.

REVISION-CLOUD EXCLUSION (spec section 11.3), as implemented here:
the text path is naturally immune -- revision clouds are vector GRAPHICS and
never appear in extracted text, so they cannot inflate a text diff. Revision
*tags* (numbered bubbles) do carry text, but no bare-token filter is applied,
deliberately: a filter broad enough to catch "1" or "A" in a tag would also
delete real content (dimensions, quantities, circuit numbers) from a panel
schedule, and silently eating real content is a worse failure than an
occasional tag-driven diff. Cloud handling on the RASTER path is a genuine open
item -- clouds are highly visible in pixels -- and is recorded as such rather
than papered over with a heuristic that has not been validated against the
golden set.
"""
from __future__ import annotations

import os
import re
import uuid

import numpy as np
from PIL import Image

from pickup_checker.models import (
    Evidence, Finding, Method, MethodParams, Provenance, Region, SheetPairing,
)

_WHITESPACE_RE = re.compile(r"\s+")

POINTS_PER_INCH = 72.0
RASTER_DPI = 150

# Evidence.crop_before_path/crop_after_path are required `str` per the frozen
# model. The text path produces no crop images, so it stores this explicit
# sentinel rather than a fabricated filesystem path that looks real but isn't.
NO_CROP = ""


def normalize_text(s: str) -> str:
    """Collapses all whitespace so comparisons are spacing-agnostic.

    Raw PDF text carries newlines and odd spacing INSIDE logical tokens; a naive
    substring/equality check against un-normalized text reports differences that
    do not exist. This is not hypothetical -- it produced a false "the model
    hallucinated this" conclusion during an earlier OCR evaluation on these same
    drawing sets.
    """
    return _WHITESPACE_RE.sub(" ", s).strip()


def _region_to_pdfplumber_bbox(region: Region) -> tuple[float, float, float, float]:
    return (
        region.x0 * POINTS_PER_INCH, region.y0 * POINTS_PER_INCH,
        region.x1 * POINTS_PER_INCH, region.y1 * POINTS_PER_INCH,
    )


def _extract_region_text(page, region: Region) -> str:
    bbox = _region_to_pdfplumber_bbox(region)
    cropped = page.crop(bbox, relative=False, strict=False)
    return cropped.extract_text() or ""


def compare_region_text(
    page_a, page_b, region: Region, pairing: SheetPairing, markup,
    doc_a_id: str, doc_b_id: str,
) -> Finding:
    """Text-first comparison. `page_a`/`page_b` are pdfplumber pages."""
    text_before = _extract_region_text(page_a, region)
    text_after = _extract_region_text(page_b, region)

    evidence = Evidence(
        text_before=text_before, text_after=text_after,
        pixel_delta_summary=None,
        crop_before_path=NO_CROP, crop_after_path=NO_CROP,
    )
    provenance = Provenance(
        doc_a_id=doc_a_id, doc_b_id=doc_b_id,
        doc_a_page=page_a.page_number - 1, doc_b_page=page_b.page_number - 1,
        registration_offset=None, registration_confidence=None,
    )
    return Finding(
        id=str(uuid.uuid4()), pairing=pairing, markup=markup, region=region,
        method=MethodParams(method=Method.TEXT_DIFF, params={}),
        evidence=evidence, provenance=provenance,
    )


def _render_region_to_pil(pdfium_page, region: Region, dpi: int = RASTER_DPI) -> Image.Image:
    scale = dpi / POINTS_PER_INCH
    bitmap = pdfium_page.render(scale=scale, rotation=0)
    full_image = bitmap.to_pil().convert("RGB")
    left = int(region.x0 * dpi)
    top = int(region.y0 * dpi)
    right = int(region.x1 * dpi)
    bottom = int(region.y1 * dpi)
    return full_image.crop((left, top, right, bottom))


def compare_region_raster(
    page_a_pdfium, page_b_pdfium, region: Region, pairing: SheetPairing, markup,
    doc_a_id: str, doc_b_id: str, out_dir: str,
) -> Finding:
    """Raster fallback. `page_a_pdfium`/`page_b_pdfium` are pypdfium2 pages.

    Writes real crop PNGs and stores a pre-computed diff ratio in
    Evidence.pixel_delta_summary -- verdict.py reads only that dict, never a
    PDF or an image, which is what keeps it PDF-library-free.
    """
    os.makedirs(out_dir, exist_ok=True)
    img_before = _render_region_to_pil(page_a_pdfium, region)
    img_after = _render_region_to_pil(page_b_pdfium, region)

    # Match sizes defensively -- registration offsets and int() truncation can
    # produce off-by-one crop dimensions; comparison requires identical shapes.
    w = min(img_before.width, img_after.width)
    h = min(img_before.height, img_after.height)
    arr_before = np.array(img_before.resize((w, h)).convert("L"), dtype=np.int16)
    arr_after = np.array(img_after.resize((w, h)).convert("L"), dtype=np.int16)

    diff = np.abs(arr_before - arr_after)
    diff_ratio = float((diff > 25).mean())  # fraction of pixels materially changed

    finding_id = str(uuid.uuid4())
    crop_before_path = os.path.join(out_dir, f"{finding_id}_before.png")
    crop_after_path = os.path.join(out_dir, f"{finding_id}_after.png")
    img_before.save(crop_before_path)
    img_after.save(crop_after_path)

    evidence = Evidence(
        text_before=None, text_after=None,
        pixel_delta_summary={"diff_ratio": diff_ratio, "width": w, "height": h},
        crop_before_path=crop_before_path, crop_after_path=crop_after_path,
    )
    provenance = Provenance(
        doc_a_id=doc_a_id, doc_b_id=doc_b_id,
        doc_a_page=0, doc_b_page=0,
        registration_offset=None, registration_confidence=None,
    )
    return Finding(
        id=finding_id, pairing=pairing, markup=markup, region=region,
        method=MethodParams(method=Method.RASTER_DIFF, params={"dpi": RASTER_DPI}),
        evidence=evidence, provenance=provenance,
    )
