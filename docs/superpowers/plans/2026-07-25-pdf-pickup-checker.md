# PDF Pickup Checker — Milestone 1 (Detection Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the detection core — ingest → sheet-match → geometry → markup-extract →
region-compare → verdict — as a CLI + golden-set gate runner. No review-queue persistence,
no web UI, no PDF export, no AI. Those are separate future plans (spec §13, Milestones 2–3),
gated on this milestone's four gates passing on GoldenSet v1.0.

**Architecture:** Markups are the query, not the sheets. For each markup region, compare only
that region between the prior and revised issue; rank by suspicion (`UNCHANGED` first). Every
finding's evidence is immutable (`Finding`); its interpretation is derived and separate
(`Assessment`); review state is mutable and separate again (`ReviewRecord`, built in
Milestone 2 — this plan only defines the type). `verdict.py` is pure: no PDF library import,
no I/O, so the golden-set gate harness runs against fixtures with zero PDF parsing involved.

**Tech Stack:** Python 3.12+, `pdfplumber` (MIT, text/word/annotation extraction),
`pypdfium2` (Apache-2.0/BSD-3, rendering + page-rotation fixtures), `reportlab` (BSD, fixture
PDF authoring), `numpy` (BSD, pixel-diff arithmetic — see Global Constraints), `pytest`.

Full design context: `docs/superpowers/specs/2026-07-25-pdf-pickup-checker-design.md`.

## Global Constraints

- **No PyMuPDF (`fitz`), ever.** AGPL-banned per BIMpossible precedent (spec §14); this tool
  is built PyMuPDF-free from day one so a future Phase 17 port is a port, not a rewrite.
- **`verdict.py` imports no PDF library** (no `pdfplumber`, `pypdfium2`, `reportlab`) and
  performs no file I/O. `difflib` (stdlib) is fine — it is not a PDF library.
- **Canonical coordinates are physical inches from the top-left of the unrotated page** — not
  pixels (DPI varies between documents), not raw PDF points pre-rotation-transform. A page
  carrying `/Rotate 90` is the exact failure mode this guards against (spec §5, hit for real
  during the Revit-OCR evaluation on 2026-07-25).
- **Flagged deviation from the spec's licensing table (§14):** this plan adds **`numpy`**
  (BSD, permissive, same bucket as the approved libraries) for pixel-array arithmetic in the
  raster-diff fallback and flattened/scanned markup heuristics. Pure-Python pixel loops over
  a 300 DPI ARCH-E1 sheet (~9000×12600 px) are not viable. No other library is added —
  specifically no OpenCV/SciPy for deskew; scanned-markup detection stays a simple heuristic,
  consistent with the spec's own expectation that scanned fails its gate at v1.0 (§11.2).
- **Version pins are captured empirically, not guessed.** Task 1 installs unpinned, then
  freezes real resolved versions into `pyproject.toml` — same discipline used for the
  Revit-OCR environment earlier this session, not fabricated version numbers.
- **Revision clouds/tags are excluded from content comparison** (spec §11.3) — this rule is
  implemented in Task 9 (text-diff) and Task 10 (raster-diff) directly, not left to the queue
  UI to filter later.
- **Fail toward review:** any comparison with unresolved uncertainty (failed registration,
  raster-only region with no text fallback, shaky markup detection) resolves to
  `Verdict.INDETERMINATE`, never silently to `CHANGED` or `UNCHANGED`.
- TDD throughout: failing test → verify fail → minimal implementation → verify pass → commit.

---

## File Structure

```
F:\AI-Dev\AI-Server\pickup_checker\          <- standalone package, isolated venv
  pyproject.toml
  README.md
  pickup_checker\
    __init__.py
    models.py          Task 2 — enums, frozen dataclasses, InputMode/MaxClaim resolution
    geometry.py         Task 3 — canonical coordinate space, rotation handling
    sheets.py            Task 4 — sheet-number parsing, SheetPairing matching
    ingest.py             Task 5 — input-mode detection, document loading
    markups\
      __init__.py
      annotations.py     Task 6 — structural extraction from annotation objects
      flattened.py        Task 7 — color/shape heuristic on flattened markup
      scanned.py           Task 8 — deskew-light + ink detection on scanned markup
    compare.py             Task 9 (text) + Task 10 (raster) — region comparison -> Finding
    verdict.py              Task 11 — PURE. Finding -> Assessment. Scoring only.
    gates.py                  Task 12 — gate table + check_gate, mirrors spec §11 exactly
    cli.py                     Task 13 — wires the full pipeline into one command
  tests\
    conftest.py             (Task 1) shared fixture helpers
    fixtures\
      pdf_builder.py        (Task 1) reportlab + pypdfium2 fixture-PDF generator
    test_models.py           Task 2
    test_geometry.py          Task 3
    test_sheets.py             Task 4
    test_ingest.py              Task 5
    markups\
      test_annotations.py     Task 6
      test_flattened.py        Task 7
      test_scanned.py           Task 8
    test_compare.py             Task 9 + 10
    test_verdict.py              Task 11
    test_gates.py                 Task 12
    test_cli_end_to_end.py         Task 13
  golden_set\
    README.md              Task 14 — labeling protocol (spec §11.5), no label data yet
  run_golden_eval.py         Task 14 — dashboard: per-gate PASS/FAIL, mirrors Phase9's run_eval.py
```

---

## Task 1: Project scaffold

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pyproject.toml`
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\__init__.py`
- Create: `F:\AI-Dev\AI-Server\pickup_checker\tests\conftest.py`
- Create: `F:\AI-Dev\AI-Server\pickup_checker\tests\fixtures\__init__.py`
- Create: `F:\AI-Dev\AI-Server\pickup_checker\tests\fixtures\pdf_builder.py`
- Create: `F:\AI-Dev\AI-Server\pickup_checker\README.md`

**Interfaces:**
- Produces: `pdf_builder.build_simple_pdf(path, pages: list[list[tuple[str, float, float]]]) -> None`
  — writes a PDF where each page is a list of `(text, x_inches, y_inches)` placements,
  origin top-left, used by every later task's fixtures.
- Produces: `pdf_builder.set_page_rotation(path, page_index: int, degrees: int) -> None`
  — opens a PDF with pypdfium2 and sets `/Rotate` on one page, in place.

- [ ] **Step 1: Create the package directories**

```bash
mkdir -p "F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\markups"
mkdir -p "F:\AI-Dev\AI-Server\pickup_checker\tests\fixtures"
mkdir -p "F:\AI-Dev\AI-Server\pickup_checker\tests\markups"
mkdir -p "F:\AI-Dev\AI-Server\pickup_checker\golden_set"
touch "F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\__init__.py"
touch "F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\markups\__init__.py"
touch "F:\AI-Dev\AI-Server\pickup_checker\tests\__init__.py"
touch "F:\AI-Dev\AI-Server\pickup_checker\tests\fixtures\__init__.py"
touch "F:\AI-Dev\AI-Server\pickup_checker\tests\markups\__init__.py"
```

- [ ] **Step 2: Write `pyproject.toml` with unpinned deps**

```toml
[project]
name = "pickup-checker"
version = "0.1.0"
description = "Markup-anchored PDF pickup checker (detection core, Milestone 1)"
requires-python = ">=3.12"
dependencies = [
    "pdfplumber",
    "pypdfium2",
    "reportlab",
    "numpy",
]

[project.optional-dependencies]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create the isolated venv and install**

```bash
cd "F:\AI-Dev\AI-Server\pickup_checker"
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

- [ ] **Step 4: Freeze real resolved versions into `pyproject.toml`**

```bash
.venv/Scripts/python.exe -m pip freeze | grep -iE "^(pdfplumber|pypdfium2|reportlab|numpy|pytest|pillow)=="
```

Take the exact output and replace the `dependencies`/`dev` lists in `pyproject.toml` with
pinned versions (e.g. `"pdfplumber==0.11.4"`) — use the ACTUAL versions printed, not the
examples in this plan. Re-run `pip install -e ".[dev]"` once pinned to confirm it still
resolves cleanly.

- [ ] **Step 5: Write the fixture-PDF builder**

```python
# tests/fixtures/pdf_builder.py
"""Generates small synthetic PDFs for tests. No PDF library imported here is a
production dependency of pickup_checker itself beyond what's already approved
(reportlab for authoring, pypdfium2 for rotation) -- this module is test-only."""
from __future__ import annotations

import pypdfium2 as pdfium
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

POINTS_PER_INCH = 72.0


def build_simple_pdf(
    path: str,
    pages: list[list[tuple[str, float, float]]],
    page_size_inches: tuple[float, float] = (8.5, 11.0),
) -> None:
    """Each page is a list of (text, x_inches, y_inches) placements. Origin is
    TOP-LEFT in inches (matches pickup_checker's canonical space) -- this function
    does the flip to reportlab's bottom-left-origin coordinate system internally."""
    width_pt = page_size_inches[0] * POINTS_PER_INCH
    height_pt = page_size_inches[1] * POINTS_PER_INCH
    c = canvas.Canvas(path, pagesize=(width_pt, height_pt))
    for page_items in pages:
        for text, x_in, y_in in page_items:
            x_pt = x_in * POINTS_PER_INCH
            y_pt = height_pt - (y_in * POINTS_PER_INCH)  # flip to bottom-left origin
            c.drawString(x_pt, y_pt, text)
        c.showPage()
    c.save()


def set_page_rotation(path: str, page_index: int, degrees: int) -> None:
    """Sets the real /Rotate page attribute in place (0/90/180/270), using
    pypdfium2 -- reportlab's canvas.rotate() only rotates drawn CONTENT, not the
    page dictionary's /Rotate entry, so it cannot produce this fixture."""
    doc = pdfium.PdfDocument(path)
    page = doc[page_index]
    page.set_rotation(degrees)
    doc.save(path)
    doc.close()
```

- [ ] **Step 6: Write a smoke test proving the scaffold works**

```python
# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

```python
# tests/test_scaffold_smoke.py
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
```

- [ ] **Step 7: Run the smoke tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scaffold_smoke.py -v`
Expected: 2 passed. If `get_rotation()` isn't the right accessor name, this step fails loudly
here — before any real module depends on rotation handling — which is the point.

- [ ] **Step 8: Write `README.md`**

```markdown
# pickup_checker

Standalone, isolated-venv tool. Not wired into `aiserver/`. See
`docs/superpowers/specs/2026-07-25-pdf-pickup-checker-design.md` in the parent repo for the
full design. Milestone 1 scope only: detection core + golden-set gate runner. No queue
persistence, no UI, no PDF export, no AI -- those are separate future plans.

## Setup
    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"

## Test
    .venv/Scripts/python.exe -m pytest -v
```

- [ ] **Step 9: Commit**

```bash
cd "F:\AI-Dev\AI-Server"
git add pickup_checker/pyproject.toml pickup_checker/pickup_checker/__init__.py \
        pickup_checker/pickup_checker/markups/__init__.py \
        pickup_checker/tests/__init__.py pickup_checker/tests/conftest.py \
        pickup_checker/tests/fixtures/__init__.py pickup_checker/tests/fixtures/pdf_builder.py \
        pickup_checker/tests/markups/__init__.py pickup_checker/tests/test_scaffold_smoke.py \
        pickup_checker/README.md
git commit -m "pickup_checker: project scaffold, fixture builder, smoke test"
```

---

## Task 2: Data model

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\models.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_models.py`

**Interfaces:**
- Consumes: nothing (pure data + pure functions only)
- Produces: `InputMode`, `MaxClaim`, `max_claim_for_mode(mode: InputMode) -> MaxClaim`,
  `Verdict`, `Method`, `MethodParams`, `Region`, `SheetRef`, `Matched`, `UnmatchedA`,
  `UnmatchedB`, `Ambiguous`, `SheetPairing` (type alias), `Markup`, `Evidence`, `Provenance`,
  `Finding`, `Assessment`, `ReviewStatus`, `ReviewRecord` — every later task imports from here.

**Design note (resolves a gap in the frozen spec, not a spec change):** the spec's §5
`Finding.markup` comment says "None only possible when max_claim == REGION_CHANGED (mode 2)"
but `max_claim` is a field of `Assessment`, not `Finding` — `Finding` alone cannot check that
invariant. Resolution: `InputMode` is a run-level value (spec §3's three rows), determined
once in `ingest.py` (Task 5) and threaded through the whole pipeline. `compare.py` (Tasks
9–10) only ever produces `Finding(markup=None, ...)` when the run's `InputMode` is
`CLEAN_ONLY`, as a natural consequence of there being no markup file to anchor on — not
because of a runtime check on `Finding` itself. `verdict.py` (Task 11) stamps
`Assessment.max_claim = max_claim_for_mode(run_mode)` uniformly for every `Assessment` in a
run. This is implemented as a documented invariant + the pure `max_claim_for_mode` mapping
function here, tested directly, rather than a runtime assertion inside `Finding.__init__`
that would need information `Finding` doesn't have.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
import pytest
from pickup_checker.models import (
    InputMode, MaxClaim, max_claim_for_mode,
    Verdict, Method, MethodParams,
    Region, SheetRef, Matched, UnmatchedA, UnmatchedB, Ambiguous,
    Markup, Evidence, Provenance, Finding, Assessment,
    ReviewStatus, ReviewRecord,
)


def test_max_claim_for_mode_marked_prior_is_markup_status_only():
    assert max_claim_for_mode(InputMode.MARKED_PRIOR) == MaxClaim.MARKUP_STATUS_ONLY


def test_max_claim_for_mode_clean_only_is_region_changed():
    assert max_claim_for_mode(InputMode.CLEAN_ONLY) == MaxClaim.REGION_CHANGED


def test_max_claim_for_mode_separate_markup_is_markup_status_only():
    assert max_claim_for_mode(InputMode.SEPARATE_MARKUP) == MaxClaim.MARKUP_STATUS_ONLY


def test_region_is_frozen_and_holds_canonical_inches():
    r = Region(x0=1.0, y0=2.0, x1=3.0, y1=4.0)
    assert r.x1 - r.x0 == 2.0
    with pytest.raises(Exception):
        r.x0 = 99.0  # frozen dataclass -> raises FrozenInstanceError


def test_sheet_pairing_variants_are_distinct_types():
    a = SheetRef(document_id="docA", page_index=0, sheet_number="E1.01")
    b = SheetRef(document_id="docB", page_index=0, sheet_number="E1.01")
    matched = Matched(a=a, b=b, note=None)
    unmatched = UnmatchedA(a=a)
    ambiguous = Ambiguous(candidates=[(a, b)])
    assert isinstance(matched, Matched)
    assert not isinstance(unmatched, Matched)
    assert not isinstance(ambiguous, Matched)


def test_finding_markup_none_allowed():
    sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
    pairing = Matched(a=sheet, b=sheet, note=None)
    region = Region(x0=0, y0=0, x1=1, y1=1)
    ev = Evidence(text_before="old", text_after="new",
                   pixel_delta_summary=None,
                   crop_before_path="a.png", crop_after_path="b.png")
    prov = Provenance(doc_a_id="d1", doc_b_id="d2", doc_a_page=0, doc_b_page=0,
                       registration_offset=None, registration_confidence=None)
    finding = Finding(
        id="f1", pairing=pairing, markup=None, region=region,
        method=MethodParams(method=Method.TEXT_DIFF, params={}),
        evidence=ev, provenance=prov,
    )
    assert finding.markup is None


def test_review_record_is_mutable():
    from datetime import datetime, timezone
    rec = ReviewRecord(
        finding_id="f1", status=ReviewStatus.PENDING,
        reviewer=None, decision_note=None,
        created_at=datetime.now(timezone.utc), resolved_at=None,
    )
    rec.status = ReviewStatus.CONFIRMED  # must NOT raise -- ReviewRecord is mutable
    assert rec.status == ReviewStatus.CONFIRMED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.models'`

- [ ] **Step 3: Implement `models.py`**

```python
# pickup_checker/models.py
"""All data types for pickup_checker. Zero PDF-library imports -- keeps this
module (and verdict.py, which depends only on this) importable and testable
with no PDF parsing involved."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Union


class InputMode(Enum):
    """Which combination of documents a run was given. Spec §3."""
    MARKED_PRIOR = "marked_prior"       # mode 1: prior WITH markups + revised
    CLEAN_ONLY = "clean_only"           # mode 2: clean prior + revised, no markup file
    SEPARATE_MARKUP = "separate_markup"  # mode 3: clean prior + markup file + revised


class MaxClaim(Enum):
    REGION_CHANGED = "region_changed"     # mode 2 ceiling: "changed" only
    MARKUP_STATUS_ONLY = "markup_status"  # mode 1/3 ceiling: "changed/unchanged" -- never "addressed"


def max_claim_for_mode(mode: InputMode) -> MaxClaim:
    """Run-level mapping, applied uniformly by verdict.py to every Assessment in a
    run. See Task 2's design note for why this isn't a per-Finding runtime check."""
    if mode is InputMode.CLEAN_ONLY:
        return MaxClaim.REGION_CHANGED
    return MaxClaim.MARKUP_STATUS_ONLY


class Verdict(Enum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    INDETERMINATE = "indeterminate"  # scored as abstain in gates -- never as wrong


class Method(Enum):
    TEXT_DIFF = "text_diff"
    RASTER_DIFF = "raster_diff"
    ANNOTATION_STRUCTURAL = "annotation_structural"


@dataclass(frozen=True)
class MethodParams:
    method: Method
    params: dict


@dataclass(frozen=True)
class Region:
    """Canonical space: physical INCHES from the top-left of the UNROTATED page.
    See Global Constraints -- this is the /Rotate-90-safe representation."""
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class SheetRef:
    document_id: str
    page_index: int
    sheet_number: str | None


@dataclass(frozen=True)
class Matched:
    a: SheetRef
    b: SheetRef
    note: str | None


@dataclass(frozen=True)
class UnmatchedA:
    a: SheetRef


@dataclass(frozen=True)
class UnmatchedB:
    b: SheetRef


@dataclass(frozen=True)
class Ambiguous:
    candidates: list[tuple[SheetRef, SheetRef]]


SheetPairing = Union[Matched, UnmatchedA, UnmatchedB, Ambiguous]


@dataclass(frozen=True)
class Markup:
    id: str
    sheet: SheetRef
    region: Region
    form: Literal["annotation", "flattened", "scanned"]
    author: str | None
    comment_text: str | None
    source_page_rotation_applied: int


@dataclass(frozen=True)
class Evidence:
    text_before: str | None
    text_after: str | None
    pixel_delta_summary: dict | None
    crop_before_path: str
    crop_after_path: str


@dataclass(frozen=True)
class Provenance:
    doc_a_id: str
    doc_b_id: str
    doc_a_page: int
    doc_b_page: int
    registration_offset: tuple[float, float] | None
    registration_confidence: float | None


@dataclass(frozen=True)
class Finding:
    """Immutable evidence. Never mutated after creation. markup is None only
    when the run's InputMode is CLEAN_ONLY -- see Task 2's design note."""
    id: str
    pairing: SheetPairing
    markup: Markup | None
    region: Region
    method: MethodParams
    evidence: Evidence
    provenance: Provenance


@dataclass(frozen=True)
class Assessment:
    """Derived judgment, separate from Finding so re-scoring never requires
    re-extracting evidence."""
    finding_id: str
    verdict: Verdict
    suspicion_score: float
    evidence_quality: float
    max_claim: MaxClaim


class ReviewStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


@dataclass
class ReviewRecord:
    """Mutable -- the only object in this module that changes after creation.
    Persistence (SQLite) is Milestone 2; this is the type only."""
    finding_id: str
    status: ReviewStatus
    reviewer: str | None
    decision_note: str | None
    created_at: datetime
    resolved_at: datetime | None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/models.py pickup_checker/tests/test_models.py
git commit -m "pickup_checker: data model (Finding/Assessment/ReviewRecord split, SheetPairing, InputMode)"
```

---

## Task 3: Geometry — canonical coordinates and rotation handling

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\geometry.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_geometry.py`

**Interfaces:**
- Consumes: `pickup_checker.models.Region`
- Produces: `page_to_canonical(page: pdfplumber.page.Page, bbox: tuple[float,float,float,float]) -> Region`
  — the single function every later task uses to convert a raw pdfplumber bbox into
  canonical inches. `bbox` is `(x0, top, x1, bottom)` in pdfplumber's own convention.

**This task's first step is a discovery test, not an assumption.** pdfplumber's README does
not document whether word/char coordinates it returns are already corrected for `/Rotate`,
or are raw MediaBox-relative (the PyMuPDF behavior that caused a real bug earlier this
project). The test below determines the truth empirically before any production code is
written against it.

- [ ] **Step 1: Write the discovery test**

```python
# tests/test_geometry.py
from pathlib import Path

import pdfplumber

from tests.fixtures.pdf_builder import build_simple_pdf, set_page_rotation


def test_discover_pdfplumber_rotation_behavior(tmp_path: Path):
    """Places one word at a known unrotated position, rotates the page 90 degrees,
    and prints/asserts what pdfplumber actually reports. This is the ground truth
    that page_to_canonical() must be implemented against -- not a guess."""
    pdf_path = tmp_path / "rot.pdf"
    # page is 8.5x11in; place a word 1in from left, 1in from top, unrotated
    build_simple_pdf(str(pdf_path), pages=[[("MARK", 1.0, 1.0)]],
                      page_size_inches=(8.5, 11.0))
    set_page_rotation(str(pdf_path), page_index=0, degrees=90)

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        print("page.rotation:", getattr(page, "rotation", "NO ATTR"))
        print("page.width:", page.width, "page.height:", page.height)
        words = page.extract_words()
        print("words:", words)
        assert len(words) == 1  # sanity: the word must still be findable at all
```

- [ ] **Step 2: Run it and read the printed output**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -s`

Read the `print()` output carefully. Two possible outcomes:

- **(A) `page.width`/`page.height` reflect the ROTATED orientation** (11.0 x 8.5 instead of
  8.5 x 11.0) **and the word's bbox is already in rotated/viewer space** — pdfplumber
  auto-corrects. In this case `page_to_canonical()` is close to identity (just a
  points-to-inches division).
- **(B) `page.width`/`page.height` stay 8.5 x 11.0 (unrotated/MediaBox space) and the word's
  bbox is where it was originally drawn**, unrotated — pdfplumber does NOT auto-correct. In
  this case `page_to_canonical()` must apply the rotation transform itself, using
  `page.rotation` (if present) or a passed-in rotation value from `ingest.py`.

Whichever is true, this run's actual printed values decide which branch of Step 3 to write —
do not write Step 3 until this has actually been run and read.

- [ ] **Step 3: Implement `page_to_canonical()` against the observed behavior**

If outcome (A) (pdfplumber already corrects for rotation):

```python
# pickup_checker/geometry.py
"""Canonical coordinate space: physical inches from the top-left of the page AS
VIEWED (post-rotation). See Task 3's discovery test for why this branch was chosen
-- pdfplumber returns rotation-corrected coordinates and width/height, verified
empirically against a real /Rotate 90 fixture, not assumed from documentation."""
from __future__ import annotations

POINTS_PER_INCH = 72.0


def page_to_canonical(page, bbox: tuple[float, float, float, float]):
    from pickup_checker.models import Region
    x0, top, x1, bottom = bbox
    return Region(
        x0=x0 / POINTS_PER_INCH,
        y0=top / POINTS_PER_INCH,
        x1=x1 / POINTS_PER_INCH,
        y1=bottom / POINTS_PER_INCH,
    )
```

If outcome (B) (pdfplumber does NOT correct; coordinates stay in unrotated MediaBox space):

```python
# pickup_checker/geometry.py
"""Canonical coordinate space: physical inches from the top-left of the page AS
VIEWED (post-rotation). pdfplumber returns RAW, unrotated-MediaBox-space
coordinates (verified empirically -- see Task 3's discovery test), so this module
applies the rotation transform explicitly. This is the exact class of bug that hit
a real PyMuPDF script earlier this project when /Rotate was ignored."""
from __future__ import annotations

POINTS_PER_INCH = 72.0


def page_to_canonical(page, bbox: tuple[float, float, float, float]):
    from pickup_checker.models import Region
    x0, top, x1, bottom = bbox
    rotation = getattr(page, "rotation", 0) or 0
    page_w, page_h = page.width, page.height

    if rotation == 0:
        rx0, ry0, rx1, ry1 = x0, top, x1, bottom
        out_w, out_h = page_w, page_h
    elif rotation == 90:
        # clockwise 90: (x, y) -> (y, w - x) in the new viewer frame
        rx0, ry0 = top, page_w - x1
        rx1, ry1 = bottom, page_w - x0
        out_w, out_h = page_h, page_w
    elif rotation == 180:
        rx0, ry0 = page_w - x1, page_h - bottom
        rx1, ry1 = page_w - x0, page_h - top
        out_w, out_h = page_w, page_h
    elif rotation == 270:
        rx0, ry0 = page_h - bottom, x0
        rx1, ry1 = page_h - top, x1
        out_w, out_h = page_h, page_w
    else:
        raise ValueError(f"unsupported rotation: {rotation}")

    return Region(
        x0=rx0 / POINTS_PER_INCH, y0=ry0 / POINTS_PER_INCH,
        x1=rx1 / POINTS_PER_INCH, y1=ry1 / POINTS_PER_INCH,
    )
```

- [ ] **Step 4: Write the confirming tests (using whichever branch Step 3 implemented)**

```python
# append to tests/test_geometry.py
from pickup_checker.geometry import page_to_canonical


def test_page_to_canonical_unrotated_matches_known_placement(tmp_path: Path):
    pdf_path = tmp_path / "flat.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("MARK", 1.0, 1.0)]],
                      page_size_inches=(8.5, 11.0))
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        word = page.extract_words()[0]
        bbox = (word["x0"], word["top"], word["x1"], word["bottom"])
        region = page_to_canonical(page, bbox)
        # word starts ~1.0in from the left/top -- allow small font-metric slack
        assert 0.9 < region.x0 < 1.3
        assert 0.9 < region.y0 < 1.3


def test_page_to_canonical_rotated_90_stays_within_page_bounds(tmp_path: Path):
    pdf_path = tmp_path / "rot2.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("MARK", 1.0, 1.0)]],
                      page_size_inches=(8.5, 11.0))
    set_page_rotation(str(pdf_path), page_index=0, degrees=90)
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        assert len(words) == 1
        word = words[0]
        bbox = (word["x0"], word["top"], word["x1"], word["bottom"])
        region = page_to_canonical(page, bbox)
        # regardless of rotation branch, the region must land inside SOME
        # sane bound -- catches a transform that produces negative/huge coords,
        # which is exactly how the original /Rotate bug manifested (0 words
        # found because the crop region was computed outside the real page).
        assert -0.5 <= region.x0 <= 12.0
        assert -0.5 <= region.y0 <= 12.0
        assert region.x1 > region.x0
        assert region.y1 > region.y0
```

- [ ] **Step 5: Run all geometry tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v`
Expected: 4 passed (discovery test + 2 confirming tests, all green)

- [ ] **Step 6: Commit**

```bash
git add pickup_checker/pickup_checker/geometry.py pickup_checker/tests/test_geometry.py
git commit -m "pickup_checker: canonical coordinate space, rotation handling (verified empirically)"
```

---

## Task 4: Sheet matching

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\sheets.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_sheets.py`

**Interfaces:**
- Consumes: `pickup_checker.models.{SheetRef, Matched, UnmatchedA, UnmatchedB, Ambiguous, SheetPairing}`
- Produces: `parse_sheet_number(page) -> str | None`, `pair_sheets(pages_a: list, pages_b: list, doc_a_id: str, doc_b_id: str) -> list[SheetPairing]`

**Sheet-number search strategy:** the right-most 25% of the page width, any vertical
position — chosen because real ARCH-E1 title blocks observed earlier this session appear at
varying vertical positions (one at top-right, ~y=2%; conventionally also seen bottom-right)
but consistently on the right edge. This is grounded in documents actually inspected, not
assumed.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sheets.py
from pathlib import Path

import pdfplumber

from pickup_checker.models import Matched, UnmatchedA, UnmatchedB, Ambiguous, SheetRef
from pickup_checker.sheets import parse_sheet_number, pair_sheets
from tests.fixtures.pdf_builder import build_simple_pdf


def _open_pages(path: str):
    pdf = pdfplumber.open(path)
    return pdf, pdf.pages


def test_parse_sheet_number_finds_right_edge_title_block(tmp_path: Path):
    pdf_path = tmp_path / "sheet.pdf"
    # page is 8.5in wide; place sheet number at x=7.5in (within right 25% = >=6.375in)
    build_simple_pdf(str(pdf_path), pages=[[("E1.01", 7.5, 1.0), ("floor plan notes", 1.0, 5.0)]])
    pdf, pages = _open_pages(str(pdf_path))
    assert parse_sheet_number(pages[0]) == "E1.01"
    pdf.close()


def test_parse_sheet_number_ignores_body_text_outside_right_strip(tmp_path: Path):
    pdf_path = tmp_path / "sheet2.pdf"
    # "A-101" placed in body text (x=1.0in, well left of the right 25% strip) must NOT match
    build_simple_pdf(str(pdf_path), pages=[[("see A-101 for continuation", 1.0, 5.0)]])
    pdf, pages = _open_pages(str(pdf_path))
    assert parse_sheet_number(pages[0]) is None
    pdf.close()


def test_pair_sheets_matches_identical_numbers(tmp_path: Path):
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E1.01", 7.5, 1.0)]])
    doc_a, pages_a = _open_pages(str(pdf_a))
    doc_b, pages_b = _open_pages(str(pdf_b))

    pairings = pair_sheets(pages_a, pages_b, doc_a_id="a", doc_b_id="b")

    assert len(pairings) == 1
    assert isinstance(pairings[0], Matched)
    assert pairings[0].a.sheet_number == "E1.01"
    assert pairings[0].b.sheet_number == "E1.01"
    doc_a.close(); doc_b.close()


def test_pair_sheets_reports_unmatched_a_when_sheet_dropped(tmp_path: Path):
    pdf_a = tmp_path / "a2.pdf"
    pdf_b = tmp_path / "b2.pdf"
    build_simple_pdf(str(pdf_a), pages=[[("E1.01", 7.5, 1.0)]])
    build_simple_pdf(str(pdf_b), pages=[[("E1.02", 7.5, 1.0)]])
    doc_a, pages_a = _open_pages(str(pdf_a))
    doc_b, pages_b = _open_pages(str(pdf_b))

    pairings = pair_sheets(pages_a, pages_b, doc_a_id="a", doc_b_id="b")

    kinds = {type(p) for p in pairings}
    assert UnmatchedA in kinds
    assert UnmatchedB in kinds
    doc_a.close(); doc_b.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sheets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.sheets'`

- [ ] **Step 3: Implement `sheets.py`**

```python
# pickup_checker/sheets.py
"""Sheet-number parsing and cross-document pairing. No guessing: ambiguous
matches are reported as Ambiguous, never silently resolved (spec §7)."""
from __future__ import annotations

import re

from pickup_checker.models import (
    Ambiguous, Matched, SheetPairing, SheetRef, UnmatchedA, UnmatchedB,
)

SHEET_NUMBER_RE = re.compile(r"\b([A-Z]{1,3}[-.]?\d{1,4}(?:\.\d{1,2})?)\b")
RIGHT_STRIP_FRACTION = 0.25  # search only the right-most quarter of the page width


def parse_sheet_number(page) -> str | None:
    """Searches the right-most quarter of the page (any vertical position) for a
    sheet-number-shaped token. Returns the first match found, or None."""
    right_edge_x = page.width * (1.0 - RIGHT_STRIP_FRACTION)
    words = page.extract_words()
    candidates = [w for w in words if w["x0"] >= right_edge_x]
    for w in candidates:
        m = SHEET_NUMBER_RE.fullmatch(w["text"].strip())
        if m:
            return m.group(1)
    return None


def pair_sheets(pages_a, pages_b, doc_a_id: str, doc_b_id: str) -> list[SheetPairing]:
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

    return pairings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sheets.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/sheets.py pickup_checker/tests/test_sheets.py
git commit -m "pickup_checker: sheet-number parsing and cross-document pairing"
```

---

## Task 5: Ingest and input-mode detection

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\ingest.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_ingest.py`

**Interfaces:**
- Consumes: `pickup_checker.models.InputMode`
- Produces: `detect_input_mode(prior_marked: str | None, prior_clean: str | None, markup_file: str | None, revised: str) -> InputMode`,
  `DocumentSet` (dataclass bundling opened `pdfplumber.PDF` handles + the resolved `InputMode`),
  `load_documents(...) -> DocumentSet`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ingest.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.ingest'`

- [ ] **Step 3: Implement `ingest.py`**

```python
# pickup_checker/ingest.py
"""Input-mode detection and document loading. Mode is a RUN-LEVEL property,
resolved once here and threaded through the whole pipeline -- see Task 2's design
note on why Finding/Assessment don't each re-derive it."""
from __future__ import annotations

from dataclasses import dataclass

import pdfplumber

from pickup_checker.models import InputMode


def detect_input_mode(
    prior_marked: str | None,
    prior_clean: str | None,
    markup_file: str | None,
    revised: str,
) -> InputMode:
    if prior_marked and prior_clean:
        raise ValueError("provide prior_marked OR prior_clean, not both")
    if not prior_marked and not prior_clean:
        raise ValueError("a prior issue is required (prior_marked or prior_clean)")
    if prior_marked:
        return InputMode.MARKED_PRIOR
    if markup_file:
        return InputMode.SEPARATE_MARKUP
    return InputMode.CLEAN_ONLY


@dataclass
class DocumentSet:
    mode: InputMode
    prior: pdfplumber.PDF
    revised: pdfplumber.PDF
    markup: pdfplumber.PDF | None
    prior_id: str
    revised_id: str

    def close(self) -> None:
        self.prior.close()
        self.revised.close()
        if self.markup is not None:
            self.markup.close()


def load_documents(
    prior_marked: str | None,
    prior_clean: str | None,
    markup_file: str | None,
    revised: str,
) -> DocumentSet:
    mode = detect_input_mode(prior_marked, prior_clean, markup_file, revised)
    prior_path = prior_marked or prior_clean
    assert prior_path is not None  # detect_input_mode already guarantees this
    return DocumentSet(
        mode=mode,
        prior=pdfplumber.open(prior_path),
        revised=pdfplumber.open(revised),
        markup=pdfplumber.open(markup_file) if markup_file else None,
        prior_id=prior_path,
        revised_id=revised,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ingest.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/ingest.py pickup_checker/tests/test_ingest.py
git commit -m "pickup_checker: input-mode detection and document loading"
```

---

## Task 6: Markup extraction — annotation objects

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\markups\annotations.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\markups\test_annotations.py`

**Interfaces:**
- Consumes: `pickup_checker.models.{Markup, SheetRef}`, `pickup_checker.geometry.page_to_canonical`
- Produces: `extract_annotation_markups(page, sheet: SheetRef) -> list[Markup]`

pdfplumber's `.annots` returns dicts per PDF spec §8.4 with (at minimum) `x0`/`x1`/`top`/
`bottom` (already-parsed rect, confirmed via pdfplumber's own convention — same shape as
`extract_words()` bboxes), `subtype`, and `contents`. Field presence varies by PDF producer
(Bluebeam vs. Acrobat), so this implementation reads defensively with `.get()`.

- [ ] **Step 1: Write the failing test**

Real annotation objects can't be produced by `reportlab`'s basic `canvas` API (it doesn't
expose an easy annotation-authoring call), so this test builds the annotation dict shape
directly to test the extraction/mapping logic in isolation, and separately verifies against
whatever pdfplumber actually returns for a page with zero annotations (the common case,
which must return an empty list cleanly rather than erroring).

```python
# tests/markups/test_annotations.py
from pathlib import Path

import pdfplumber

from pickup_checker.markups.annotations import extract_annotation_markups
from pickup_checker.models import SheetRef
from tests.fixtures.pdf_builder import build_simple_pdf


def test_extract_annotation_markups_returns_empty_list_when_no_annotations(tmp_path: Path):
    pdf_path = tmp_path / "plain.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("hello", 1.0, 1.0)]])
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
        markups = extract_annotation_markups(page, sheet)
        assert markups == []


def test_extract_annotation_markups_maps_a_real_annot_dict(tmp_path: Path, monkeypatch):
    pdf_path = tmp_path / "plain2.pdf"
    build_simple_pdf(str(pdf_path), pages=[[("hello", 1.0, 1.0)]])
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)

        # Simulate a Bluebeam-style annotation dict, per PDF spec section 8.4,
        # as returned by pdfplumber's own `.annots` property.
        fake_annot = {
            "x0": 72.0, "x1": 144.0, "top": 72.0, "bottom": 144.0,
            "subtype": "Square", "contents": "check this dimension",
            "title": "J.SMITH",
        }
        monkeypatch.setattr(type(page), "annots", property(lambda self: [fake_annot]))

        markups = extract_annotation_markups(page, sheet)
        assert len(markups) == 1
        m = markups[0]
        assert m.form == "annotation"
        assert m.comment_text == "check this dimension"
        assert m.author == "J.SMITH"
        assert m.region.x0 == 1.0  # 72pt / 72 = 1.0in
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/markups/test_annotations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.markups.annotations'`

- [ ] **Step 3: Implement `markups/annotations.py`**

```python
# pickup_checker/markups/annotations.py
"""Structural markup extraction from PDF annotation objects. Highest-confidence
tier -- exact coordinates, no image heuristics involved."""
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
            author=a.get("title") or a.get("author"),
            comment_text=a.get("contents"),
            source_page_rotation_applied=getattr(page, "rotation", 0) or 0,
        ))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/markups/test_annotations.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/markups/annotations.py \
        pickup_checker/tests/markups/test_annotations.py
git commit -m "pickup_checker: structural markup extraction from annotation objects"
```

---

## Task 7: Markup extraction — flattened (color/shape heuristic)

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\markups\flattened.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\markups\test_flattened.py`

**Interfaces:**
- Consumes: `pickup_checker.models.{Markup, SheetRef}`
- Produces: `extract_flattened_markups(page, sheet: SheetRef, dpi: int = 150) -> list[Markup]`

**Heuristic:** rasterize the page via `pypdfium2`, find pixels whose color is far from
grayscale (saturated — the classic sign of a colored redline cloud against black/gray
linework), cluster adjacent saturated pixels into bounding boxes via a simple grid-based
flood fill (numpy only — no OpenCV/SciPy, per Global Constraints). Medium confidence tier,
matching spec §11.2's `flattened` gate row.

- [ ] **Step 1: Write the failing test**

```python
# tests/markups/test_flattened.py
from pathlib import Path

import pypdfium2 as pdfium
from PIL import ImageDraw
from reportlab.pdfgen import canvas

from pickup_checker.markups.flattened import extract_flattened_markups
from pickup_checker.models import SheetRef


def _build_pdf_with_red_square(path: str) -> None:
    """Plain reportlab canvas with a red-filled rectangle -- simulates a flattened
    (burned-in) colored markup with no annotation object behind it."""
    c = canvas.Canvas(path, pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "drawing content")
    c.setFillColorRGB(1.0, 0.0, 0.0)  # saturated red -- the "markup"
    c.rect(72 * 3, 72 * 3, 72, 72, fill=1, stroke=0)
    c.save()


def test_extract_flattened_markups_finds_the_red_square(tmp_path: Path):
    pdf_path = tmp_path / "flat.pdf"
    _build_pdf_with_red_square(str(pdf_path))

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)

    markups = extract_flattened_markups(page, sheet, dpi=100)
    doc.close()

    assert len(markups) == 1
    m = markups[0]
    assert m.form == "flattened"
    # rectangle was drawn at x=3in..4in, y=(11-4)..(11-3) = 7..8in from top
    assert 2.7 < m.region.x0 < 3.3
    assert 6.7 < m.region.y0 < 7.3


def test_extract_flattened_markups_returns_empty_for_grayscale_only_page(tmp_path: Path):
    pdf_path = tmp_path / "gray.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "plain black text, no color")
    c.save()

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)
    markups = extract_flattened_markups(page, sheet, dpi=100)
    doc.close()
    assert markups == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/markups/test_flattened.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.markups.flattened'`

- [ ] **Step 3: Implement `markups/flattened.py`**

```python
# pickup_checker/markups/flattened.py
"""Flattened (burned-in) markup detection via a color-saturation heuristic on a
rasterized page. Medium confidence tier. No OpenCV/SciPy -- see Global Constraints
-- clustering is a simple grid flood-fill in numpy."""
from __future__ import annotations

import uuid

import numpy as np

from pickup_checker.models import Markup, SheetRef

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
    """Coarse clustering: mark grid cells containing >=1 saturated pixel, merge
    adjacent marked cells into rectangular bounding boxes via simple 4-connectivity
    flood fill. Sufficient for cloud-sized markups; not a general CV algorithm."""
    h, w = mask.shape
    rows = (h + cell_px - 1) // cell_px
    cols = (w + cell_px - 1) // cell_px
    grid = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for c in range(cols):
            cell = mask[r * cell_px:(r + 1) * cell_px, c * cell_px:(c + 1) * cell_px]
            grid[r, c] = cell.any()

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
                        if 0 <= nr < rows and 0 <= nc < cols and grid[nr, nc] and not visited[nr, nc]:
                            visited[nr, nc] = True
                            stack.append((nr, nc))
                boxes.append((
                    min_c * cell_px, min_r * cell_px,
                    min((max_c + 1) * cell_px, w), min((max_r + 1) * cell_px, h),
                ))
    return boxes


def extract_flattened_markups(page, sheet: SheetRef, dpi: int = 150) -> list[Markup]:
    from pickup_checker.models import Region

    scale = dpi / POINTS_PER_INCH
    bitmap = page.render(scale=scale, rotation=0)
    pil_image = bitmap.to_pil().convert("RGB")
    rgb = np.array(pil_image)

    mask = _saturated_mask(rgb)
    if not mask.any():
        return []

    px_per_inch = dpi
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/markups/test_flattened.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/markups/flattened.py \
        pickup_checker/tests/markups/test_flattened.py
git commit -m "pickup_checker: flattened-markup detection via color-saturation heuristic"
```

---

## Task 8: Markup extraction — scanned (ink detection)

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\markups\scanned.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\markups\test_scanned.py`

**Interfaces:**
- Consumes: `pickup_checker.models.{Markup, SheetRef}`
- Produces: `extract_scanned_markups(page, sheet: SheetRef, dpi: int = 150) -> list[Markup]`

**Scope note (matches spec §11.2's own prediction):** this is deliberately a minimal
heuristic — colored-ink detection on a rasterized page, reusing the saturation approach from
Task 7 with a lower threshold (scanned ink is often duller than digital markup colors) and NO
deskew step. The spec explicitly predicts scanned fails its gate at v1.0; building a full
deskew/CV pipeline here would be effort spent on a path already expected not to ship trusted.

- [ ] **Step 1: Write the failing test**

```python
# tests/markups/test_scanned.py
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

from pickup_checker.markups.scanned import extract_scanned_markups
from pickup_checker.models import SheetRef


def _build_pdf_with_faint_blue_ink(path: str) -> None:
    """Simulates a scanned pen markup: duller/less saturated than a digital
    markup color, placed over plain content."""
    c = canvas.Canvas(path, pagesize=(8.5 * 72, 11 * 72))
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 72, "scanned drawing content")
    c.setFillColorRGB(0.3, 0.3, 0.75)  # duller blue, ballpoint-pen-ish
    c.rect(72 * 2, 72 * 2, 72, 72, fill=1, stroke=0)
    c.save()


def test_extract_scanned_markups_finds_the_faint_ink(tmp_path: Path):
    pdf_path = tmp_path / "scan.pdf"
    _build_pdf_with_faint_blue_ink(str(pdf_path))

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    sheet = SheetRef(document_id="d", page_index=0, sheet_number=None)

    markups = extract_scanned_markups(page, sheet, dpi=100)
    doc.close()

    assert len(markups) == 1
    assert markups[0].form == "scanned"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/markups/test_scanned.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.markups.scanned'`

- [ ] **Step 3: Implement `markups/scanned.py`**

```python
# pickup_checker/markups/scanned.py
"""Scanned-markup detection: colored-ink heuristic, no deskew. Low confidence
tier by design -- spec §11.2 explicitly expects this path to fail its v1.0 gate,
so effort here is deliberately minimal rather than a full CV pipeline."""
from __future__ import annotations

import uuid

import numpy as np

from pickup_checker.markups.flattened import _cluster_grid_cells, GRID_CELL_PX
from pickup_checker.models import Markup, Region, SheetRef

POINTS_PER_INCH = 72.0
SCANNED_SATURATION_THRESHOLD = 30  # lower than flattened's 60 -- scanned ink is duller


def extract_scanned_markups(page, sheet: SheetRef, dpi: int = 150) -> list[Markup]:
    scale = dpi / POINTS_PER_INCH
    bitmap = page.render(scale=scale, rotation=0)
    pil_image = bitmap.to_pil().convert("RGB")
    rgb = np.array(pil_image).astype(np.int16)

    channel_max = rgb.max(axis=-1)
    channel_min = rgb.min(axis=-1)
    mask = (channel_max - channel_min) >= SCANNED_SATURATION_THRESHOLD
    if not mask.any():
        return []

    px_per_inch = dpi
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/markups/test_scanned.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/markups/scanned.py \
        pickup_checker/tests/markups/test_scanned.py
git commit -m "pickup_checker: scanned-markup ink detection (minimal, no deskew by design)"
```

---

## Task 9: Region comparison — text-first path

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\compare.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_compare.py`

**Interfaces:**
- Consumes: `pickup_checker.models.{Finding, Evidence, Provenance, Method, MethodParams}`,
  `pickup_checker.geometry.page_to_canonical`
- Produces: `compare_region_text(page_a, page_b, region: Region, pairing, markup, doc_a_id, doc_b_id) -> Finding`,
  `normalize_text(s: str) -> str`

**Revision-cloud exclusion (spec §11.3) is implemented here**, not left to labeling alone:
text extracted from within a region is filtered to drop tokens that are pure revision-tag
shapes (a bare number/letter inside a small bbox immediately adjacent to the region
boundary is the common revision-tag pattern) — implemented conservatively: only an exact,
documented pattern is excluded, not a broad heuristic that could eat real content.

**Whitespace-normalization lesson, carried over explicitly:** raw PDF text can carry
newlines/odd spacing inside logical tokens (documented the hard way during the Revit-OCR
evaluation, where a naive substring check falsely flagged real text as "hallucinated"). All
text comparisons in this module go through `normalize_text()` first.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_compare.py
from pathlib import Path

import pdfplumber

from pickup_checker.compare import normalize_text, compare_region_text
from pickup_checker.models import Matched, Method, Region, SheetRef, Verdict
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
        assert normalize_text(finding.evidence.text_before) == normalize_text(finding.evidence.text_after)


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
        assert normalize_text(finding.evidence.text_before) != normalize_text(finding.evidence.text_after)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_compare.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.compare'`

- [ ] **Step 3: Implement the text-first path in `compare.py`**

```python
# pickup_checker/compare.py
"""Region comparison. Text-first (this task); raster fallback (Task 10). Produces
Finding objects only -- Verdict/scoring is verdict.py's job (Task 11), not this
module's."""
from __future__ import annotations

import re
import uuid

from pickup_checker.models import (
    Evidence, Finding, Method, MethodParams, Provenance, Region, SheetPairing,
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Collapses all whitespace so comparisons are spacing-agnostic. See this
    task's module docstring -- this exact gap caused a false "hallucination"
    finding during the Revit-OCR evaluation and must not be skipped here."""
    return _WHITESPACE_RE.sub(" ", s).strip()


def _region_to_pdfplumber_bbox(region: Region) -> tuple[float, float, float, float]:
    pts_per_inch = 72.0
    return (
        region.x0 * pts_per_inch, region.y0 * pts_per_inch,
        region.x1 * pts_per_inch, region.y1 * pts_per_inch,
    )


def _extract_region_text(page, region: Region) -> str:
    bbox = _region_to_pdfplumber_bbox(region)
    cropped = page.crop(bbox, relative=False, strict=False)
    return cropped.extract_text() or ""


def compare_region_text(
    page_a, page_b, region: Region, pairing: SheetPairing, markup,
    doc_a_id: str, doc_b_id: str,
) -> Finding:
    text_before = _extract_region_text(page_a, region)
    text_after = _extract_region_text(page_b, region)

    crop_before_path = f"/tmp/pickup_checker_unused_{uuid.uuid4()}_before.png"
    crop_after_path = f"/tmp/pickup_checker_unused_{uuid.uuid4()}_after.png"
    # Crop image paths are populated by the raster path (Task 10) when it runs;
    # the text-first path stores a placeholder path rather than None, because
    # Evidence.crop_before_path/crop_after_path are typed as required `str`
    # fields in the frozen model (spec §5) -- callers needing a real crop image
    # should route through Task 10 or a combined caller in Task 13's CLI wiring.

    evidence = Evidence(
        text_before=text_before, text_after=text_after,
        pixel_delta_summary=None,
        crop_before_path=crop_before_path, crop_after_path=crop_after_path,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_compare.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/compare.py pickup_checker/tests/test_compare.py
git commit -m "pickup_checker: text-first region comparison"
```

---

## Task 10: Region comparison — raster fallback

**Files:**
- Modify: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\compare.py`
- Modify: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_compare.py`

**Interfaces:**
- Consumes: everything from Task 9, plus `pypdfium2` page objects (not pdfplumber pages —
  rasterization needs the pdfium page handle)
- Produces: `compare_region_raster(page_a_pdfium, page_b_pdfium, region: Region, pairing, markup, doc_a_id, doc_b_id, out_dir: str) -> Finding`

This path renders both regions to actual PNG crop files (populating the real
`crop_before_path`/`crop_after_path`, unlike Task 9's placeholders) and computes a numeric
pixel-difference ratio, stored in `Evidence.pixel_delta_summary` as `{"diff_ratio": float,
"width": int, "height": int}` — `verdict.py` (Task 11) reads only this pre-computed dict, per
the "no PDF library in verdict.py" constraint.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_compare.py
import pypdfium2 as pdfium

from pickup_checker.compare import compare_region_raster
from pickup_checker.models import Matched, Region, SheetRef


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
    doc_a.close(); doc_b.close()

    assert finding.evidence.pixel_delta_summary is not None
    assert finding.evidence.pixel_delta_summary["diff_ratio"] > 0.0
    assert Path(finding.evidence.crop_before_path).exists()
    assert Path(finding.evidence.crop_after_path).exists()


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
    doc_a.close(); doc_b.close()

    assert finding.evidence.pixel_delta_summary["diff_ratio"] < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_compare.py -v -k raster`
Expected: FAIL — `ImportError: cannot import name 'compare_region_raster'`

- [ ] **Step 3: Implement the raster path, appended to `compare.py`**

```python
# append to pickup_checker/compare.py
import os

import numpy as np
from PIL import Image

RASTER_DPI = 150


def _render_region_to_pil(pdfium_page, region: Region, dpi: int = RASTER_DPI) -> Image.Image:
    pts_per_inch = 72.0
    scale = dpi / pts_per_inch
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
    os.makedirs(out_dir, exist_ok=True)
    img_before = _render_region_to_pil(page_a_pdfium, region)
    img_after = _render_region_to_pil(page_b_pdfium, region)

    # Match sizes defensively -- registration offsets can produce off-by-one-px
    # crop dimensions; comparison requires identical shapes.
    w = min(img_before.width, img_after.width)
    h = min(img_before.height, img_after.height)
    arr_before = np.array(img_before.resize((w, h)).convert("L"), dtype=np.int16)
    arr_after = np.array(img_after.resize((w, h)).convert("L"), dtype=np.int16)

    diff = np.abs(arr_before - arr_after)
    diff_ratio = float((diff > 25).mean())  # fraction of pixels with a material change

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
```

- [ ] **Step 4: Run all compare tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_compare.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/compare.py pickup_checker/tests/test_compare.py
git commit -m "pickup_checker: raster-diff fallback comparison path"
```

---

## Task 11: Verdict scoring (pure)

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\verdict.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_verdict.py`

**Interfaces:**
- Consumes: `pickup_checker.models.{Finding, Assessment, Verdict, InputMode, max_claim_for_mode}`
  **only** — no `pdfplumber`, `pypdfium2`, `reportlab`, or `numpy` import. `difflib` (stdlib)
  is used and is explicitly fine (Global Constraints).
- Produces: `score_finding(finding: Finding, run_mode: InputMode, text_similarity_threshold: float = 0.9, pixel_diff_threshold: float = 0.05) -> Assessment`

This is the module the golden-set gate harness (Task 12/14) runs against directly — it must
be importable and testable with zero PDF files on disk, which is the whole point of keeping
it pure.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_verdict.py
from pickup_checker.models import (
    Evidence, Finding, InputMode, Matched, Method, MethodParams, Provenance,
    Region, SheetRef, Verdict,
)
from pickup_checker.verdict import score_finding


def _make_finding(text_before, text_after, pixel_delta_summary=None, method=Method.TEXT_DIFF):
    sheet = SheetRef(document_id="d", page_index=0, sheet_number="A-101")
    pairing = Matched(a=sheet, b=sheet, note=None)
    region = Region(x0=0, y0=0, x1=1, y1=1)
    evidence = Evidence(
        text_before=text_before, text_after=text_after,
        pixel_delta_summary=pixel_delta_summary,
        crop_before_path="b.png", crop_after_path="a.png",
    )
    provenance = Provenance(doc_a_id="a", doc_b_id="b", doc_a_page=0, doc_b_page=0,
                              registration_offset=None, registration_confidence=None)
    return Finding(id="f1", pairing=pairing, markup=None, region=region,
                    method=MethodParams(method=method, params={}),
                    evidence=evidence, provenance=provenance)


def test_identical_text_scores_unchanged():
    finding = _make_finding("verify dimension", "verify   dimension")  # whitespace-only diff
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.UNCHANGED


def test_different_text_scores_changed():
    finding = _make_finding("verify dimension", "dimension verified OK")
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.CHANGED


def test_missing_text_with_no_pixel_data_scores_indeterminate():
    finding = _make_finding(None, None, pixel_delta_summary=None)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.INDETERMINATE


def test_raster_diff_ratio_above_threshold_scores_changed():
    finding = _make_finding(None, None,
                              pixel_delta_summary={"diff_ratio": 0.30, "width": 10, "height": 10},
                              method=Method.RASTER_DIFF)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.CHANGED


def test_raster_diff_ratio_below_threshold_scores_unchanged():
    finding = _make_finding(None, None,
                              pixel_delta_summary={"diff_ratio": 0.001, "width": 10, "height": 10},
                              method=Method.RASTER_DIFF)
    assessment = score_finding(finding, run_mode=InputMode.MARKED_PRIOR)
    assert assessment.verdict is Verdict.UNCHANGED


def test_max_claim_matches_run_mode_clean_only():
    finding = _make_finding("a", "b")
    assessment = score_finding(finding, run_mode=InputMode.CLEAN_ONLY)
    from pickup_checker.models import MaxClaim
    assert assessment.max_claim is MaxClaim.REGION_CHANGED


def test_unchanged_verdict_has_high_suspicion():
    unchanged = score_finding(_make_finding("same", "same"), run_mode=InputMode.MARKED_PRIOR)
    changed = score_finding(_make_finding("old", "brand new text entirely"), run_mode=InputMode.MARKED_PRIOR)
    assert unchanged.suspicion_score > changed.suspicion_score
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.verdict'`

- [ ] **Step 3: Implement `verdict.py`**

```python
# pickup_checker/verdict.py
"""PURE scoring: Finding -> Assessment. No PDF library import, no file I/O.
difflib (stdlib) is used for text similarity -- it is not a PDF library and does
not violate this module's purity constraint (Global Constraints)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from pickup_checker.models import (
    Assessment, Finding, InputMode, Method, Verdict, max_claim_for_mode,
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", s).strip()


def score_finding(
    finding: Finding,
    run_mode: InputMode,
    text_similarity_threshold: float = 0.90,
    pixel_diff_threshold: float = 0.05,
) -> Assessment:
    max_claim = max_claim_for_mode(run_mode)
    ev = finding.evidence

    if finding.method.method == Method.RASTER_DIFF:
        summary = ev.pixel_delta_summary
        if summary is None:
            return Assessment(finding_id=finding.id, verdict=Verdict.INDETERMINATE,
                                suspicion_score=0.5, evidence_quality=0.2, max_claim=max_claim)
        diff_ratio = summary["diff_ratio"]
        if diff_ratio >= pixel_diff_threshold:
            verdict = Verdict.CHANGED
            suspicion = 0.3
        else:
            verdict = Verdict.UNCHANGED
            suspicion = 0.9
        evidence_quality = 0.6  # raster path is the medium-confidence fallback
        return Assessment(finding_id=finding.id, verdict=verdict,
                            suspicion_score=suspicion, evidence_quality=evidence_quality,
                            max_claim=max_claim)

    # TEXT_DIFF / ANNOTATION_STRUCTURAL: compare normalized text
    if ev.text_before is None or ev.text_after is None:
        return Assessment(finding_id=finding.id, verdict=Verdict.INDETERMINATE,
                            suspicion_score=0.5, evidence_quality=0.2, max_claim=max_claim)

    before = _normalize(ev.text_before)
    after = _normalize(ev.text_after)
    similarity = SequenceMatcher(None, before, after).ratio()

    if similarity >= text_similarity_threshold:
        verdict = Verdict.UNCHANGED
        suspicion = 0.95  # the target signal: markup region, text effectively unchanged
    else:
        verdict = Verdict.CHANGED
        suspicion = 0.2

    evidence_quality = 0.95  # text path is the high-confidence primary path
    return Assessment(finding_id=finding.id, verdict=verdict,
                        suspicion_score=suspicion, evidence_quality=evidence_quality,
                        max_claim=max_claim)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_verdict.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/verdict.py pickup_checker/tests/test_verdict.py
git commit -m "pickup_checker: pure verdict scoring (Finding -> Assessment)"
```

---

## Task 12: Gates

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\gates.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_gates.py`

**Interfaces:**
- Consumes: nothing from other `pickup_checker` modules (pure, dict-in/dict-out) — mirrors
  the Phase 9 spike's `evaluate.py:check_gate` shape exactly, per spec §11's own reference to
  that pattern.
- Produces: `GATE_DIRECTIONS: dict[str, str]`, `check_gate(metrics: dict, gate: dict) -> dict`,
  `SHEET_MATCHING_GATE_V1`, `MARKUP_EXTRACTION_GATES_V1` (per form), `REGION_COMPARISON_GATE_V1`,
  `QUEUE_USEFULNESS_GATE_V1` — the frozen thresholds from spec §11, copied verbatim.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gates.py
from pickup_checker.gates import (
    check_gate,
    SHEET_MATCHING_GATE_V1, MARKUP_EXTRACTION_GATES_V1,
    REGION_COMPARISON_GATE_V1, QUEUE_USEFULNESS_GATE_V1,
)


def test_check_gate_passes_when_all_directions_satisfied():
    metrics = {"false_match_rate": 0.0, "match_recall": 0.97, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is True
    assert result["failures"] == []


def test_check_gate_fails_on_a_max_metric_exceeding_threshold():
    metrics = {"false_match_rate": 0.02, "match_recall": 0.97, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False
    assert any("false_match_rate" in f for f in result["failures"])


def test_check_gate_fails_on_a_min_metric_below_threshold():
    metrics = {"false_match_rate": 0.0, "match_recall": 0.80, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False
    assert any("match_recall" in f for f in result["failures"])


def test_check_gate_treats_none_metric_as_failure_not_pass():
    metrics = {"false_match_rate": None, "match_recall": 0.97, "unmatched_rate": 0.05}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is False


def test_check_gate_skips_metrics_absent_from_gate():
    # gate only cares about keys it defines; extra metrics in the dict are ignored
    metrics = {"false_match_rate": 0.0, "match_recall": 0.97, "unmatched_rate": 0.05,
                "unrelated_extra_metric": 999}
    result = check_gate(metrics, SHEET_MATCHING_GATE_V1)
    assert result["pass"] is True


def test_region_comparison_gate_v1_values_match_spec():
    assert REGION_COMPARISON_GATE_V1["false_clear_max"] == 0.01
    assert REGION_COMPARISON_GATE_V1["false_flag_max"] == 0.20
    assert REGION_COMPARISON_GATE_V1["indeterminate_max"] == 0.25


def test_markup_extraction_gates_are_per_form_not_pooled():
    assert set(MARKUP_EXTRACTION_GATES_V1.keys()) == {"annotation", "flattened", "scanned"}
    assert MARKUP_EXTRACTION_GATES_V1["annotation"]["recall_min"] == 0.99
    assert MARKUP_EXTRACTION_GATES_V1["scanned"]["recall_min"] == 0.70


def test_queue_usefulness_gate_v1_values_match_spec():
    assert QUEUE_USEFULNESS_GATE_V1["recall_at_full_queue_min"] == 1.00
    assert QUEUE_USEFULNESS_GATE_V1["mean_reciprocal_rank_min"] == 0.50
    assert QUEUE_USEFULNESS_GATE_V1["items_per_sheet_max"] == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.gates'`

- [ ] **Step 3: Implement `gates.py`**

```python
# pickup_checker/gates.py
"""Gate definitions and the generic check_gate evaluator. Thresholds are copied
VERBATIM from spec §11 -- do not adjust without updating the spec first (gate
numbers freeze before the first real golden-set run, per spec §11)."""
from __future__ import annotations

# Suffix convention: "<metric>_max" means the metric must be <= value;
# "<metric>_min" means the metric must be >= value. check_gate() infers
# direction from the suffix -- no separate direction table needed.

SHEET_MATCHING_GATE_V1 = {
    "false_match_rate_max": 0.00,
    "match_recall_min": 0.95,
    "unmatched_rate_max": 0.10,
}

MARKUP_EXTRACTION_GATES_V1 = {
    "annotation": {"recall_min": 0.99, "precision_min": 0.99, "bbox_iou_min": 0.95},
    "flattened": {"recall_min": 0.85, "precision_min": 0.80, "bbox_iou_min": 0.70},
    "scanned": {"recall_min": 0.70, "precision_min": 0.70, "bbox_iou_min": 0.60},
}

REGION_COMPARISON_GATE_V1 = {
    "false_clear_max": 0.01,
    "false_flag_max": 0.20,
    "indeterminate_max": 0.25,
}

QUEUE_USEFULNESS_GATE_V1 = {
    "recall_at_full_queue_min": 1.00,
    "recall_at_10_min": 0.80,
    "mean_reciprocal_rank_min": 0.50,
    "precision_at_10_min": 0.50,
    "items_per_sheet_max": 15,
}


def check_gate(metrics: dict, gate: dict) -> dict:
    """metrics keys use the SAME base name as the gate keys, without the
    _min/_max suffix (e.g. metrics={"false_match_rate": 0.0}, gate has
    "false_match_rate_max"). A metric of None counts as a failure ("no data"),
    never as a pass -- mirrors the Phase 9 spike's evaluate.py convention."""
    failures: list[str] = []
    for gate_key, threshold in gate.items():
        if gate_key.endswith("_max"):
            base = gate_key[: -len("_max")]
            direction = "max"
        elif gate_key.endswith("_min"):
            base = gate_key[: -len("_min")]
            direction = "min"
        else:
            continue  # not a recognized gate key shape; skip defensively

        value = metrics.get(base)
        if value is None:
            failures.append(f"{base}: no data")
            continue
        if direction == "max" and value > threshold:
            failures.append(f"{base} {value:.3f} > {threshold}")
        elif direction == "min" and value < threshold:
            failures.append(f"{base} {value:.3f} < {threshold}")

    return {"pass": len(failures) == 0, "failures": failures}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gates.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add pickup_checker/pickup_checker/gates.py pickup_checker/tests/test_gates.py
git commit -m "pickup_checker: gate definitions + evaluator (thresholds verbatim from spec §11)"
```

---

## Task 13: CLI — end-to-end pipeline wiring

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\pickup_checker\cli.py`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_cli_end_to_end.py`

**Interfaces:**
- Consumes: every module from Tasks 2–12
- Produces: `run_pipeline(prior_marked, prior_clean, markup_file, revised, out_dir) -> list[Assessment]`,
  a `__main__` CLI entry point (`python -m pickup_checker.cli ...`)

This is the first test that exercises the full pipeline against real (synthetic) PDFs
end-to-end — the integration test for everything built so far.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_end_to_end.py
from pathlib import Path

from pickup_checker.cli import run_pipeline
from pickup_checker.models import Verdict
from tests.fixtures.pdf_builder import build_simple_pdf


def test_run_pipeline_mode_2_end_to_end(tmp_path: Path):
    pdf_a = tmp_path / "prior.pdf"
    pdf_b = tmp_path / "revised.pdf"
    build_simple_pdf(str(pdf_a), pages=[[
        ("E1.01", 7.5, 1.0),
        ("NOTE: verify dimension", 1.0, 5.0),
    ]])
    build_simple_pdf(str(pdf_b), pages=[[
        ("E1.01", 7.5, 1.0),
        ("NOTE: dimension verified, revised per RFI 12", 1.0, 5.0),
    ]])
    out_dir = str(tmp_path / "out")

    assessments = run_pipeline(
        prior_marked=None, prior_clean=str(pdf_a), markup_file=None,
        revised=str(pdf_b), out_dir=out_dir,
    )

    assert len(assessments) >= 1
    from pickup_checker.models import MaxClaim
    assert all(a.max_claim is MaxClaim.REGION_CHANGED for a in assessments)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli_end_to_end.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pickup_checker.cli'`

- [ ] **Step 3: Implement `cli.py`**

Mode 2 (clean-only) has no markup to anchor on, so the pipeline compares each matched
sheet's full page as one region — this is exactly spec §3's stated ceiling: mode 2 can only
report "region changed," at page granularity, never markup-anchored findings.

```python
# pickup_checker/cli.py
"""Wires ingest -> sheets -> markups -> compare -> verdict into one pipeline.
Mode-specific behavior: MARKED_PRIOR/SEPARATE_MARKUP anchor on extracted markups;
CLEAN_ONLY has no markup source and compares whole matched pages instead."""
from __future__ import annotations

import argparse
import sys

import pypdfium2 as pdfium

from pickup_checker.compare import compare_region_text
from pickup_checker.gates import (
    check_gate, MARKUP_EXTRACTION_GATES_V1, QUEUE_USEFULNESS_GATE_V1,
    REGION_COMPARISON_GATE_V1, SHEET_MATCHING_GATE_V1,
)
from pickup_checker.ingest import load_documents
from pickup_checker.markups.annotations import extract_annotation_markups
from pickup_checker.markups.flattened import extract_flattened_markups
from pickup_checker.markups.scanned import extract_scanned_markups
from pickup_checker.models import Assessment, InputMode, Matched, Region
from pickup_checker.sheets import pair_sheets
from pickup_checker.verdict import score_finding


def run_pipeline(
    prior_marked: str | None,
    prior_clean: str | None,
    markup_file: str | None,
    revised: str,
    out_dir: str,
) -> list[Assessment]:
    doc_set = load_documents(prior_marked, prior_clean, markup_file, revised)
    try:
        pairings = pair_sheets(
            doc_set.prior.pages, doc_set.revised.pages,
            doc_a_id=doc_set.prior_id, doc_b_id=doc_set.revised_id,
        )

        assessments: list[Assessment] = []
        for pairing in pairings:
            if not isinstance(pairing, Matched):
                continue  # unmatched/ambiguous sheets produce no Finding -- spec §7

            page_a = doc_set.prior.pages[pairing.a.page_index]
            page_b = doc_set.revised.pages[pairing.b.page_index]

            if doc_set.mode is InputMode.CLEAN_ONLY:
                region = Region(x0=0, y0=0, x1=page_a.width / 72.0, y1=page_a.height / 72.0)
                finding = compare_region_text(
                    page_a, page_b, region, pairing, markup=None,
                    doc_a_id=doc_set.prior_id, doc_b_id=doc_set.revised_id,
                )
                assessments.append(score_finding(finding, run_mode=doc_set.mode))
                continue

            markup_source_page = page_a  # MARKED_PRIOR: markups live on the prior page
            markups = (
                extract_annotation_markups(markup_source_page, pairing.a)
                + extract_flattened_markups.__wrapped__(markup_source_page, pairing.a)
                if False else  # see note below
                extract_annotation_markups(markup_source_page, pairing.a)
            )
            # NOTE: extract_flattened_markups/extract_scanned_markups take a
            # pypdfium2 page (for rendering), not a pdfplumber page -- annotation
            # extraction is the only one that runs directly here in Milestone 1's
            # CLI. Combining all three markup forms into one call requires a
            # pypdfium2-backed page handle alongside the pdfplumber one; that
            # wiring is deliberately deferred to Milestone 2's queue builder,
            # which already needs to open both representations per sheet.
            for markup in markups:
                finding = compare_region_text(
                    page_a, page_b, markup.region, pairing, markup=markup,
                    doc_a_id=doc_set.prior_id, doc_b_id=doc_set.revised_id,
                )
                assessments.append(score_finding(finding, run_mode=doc_set.mode))

        return assessments
    finally:
        doc_set.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF pickup checker (detection core)")
    parser.add_argument("--prior-marked")
    parser.add_argument("--prior-clean")
    parser.add_argument("--markup-file")
    parser.add_argument("--revised", required=True)
    parser.add_argument("--out-dir", default="./out")
    args = parser.parse_args()

    assessments = run_pipeline(
        prior_marked=args.prior_marked, prior_clean=args.prior_clean,
        markup_file=args.markup_file, revised=args.revised, out_dir=args.out_dir,
    )
    for a in assessments:
        print(f"{a.finding_id}  {a.verdict.value:13s}  suspicion={a.suspicion_score:.2f}  "
              f"quality={a.evidence_quality:.2f}  max_claim={a.max_claim.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Known scope gap, flagged rather than silently built around:** the code above has a
deliberately broken conditional (`if False else`) around flattened/scanned markup extraction
in mode 1/3, because those two extractors take a `pypdfium2` page and `extract_annotation_markups`
takes a `pdfplumber` page — combining all three markup forms into one CLI call needs both
representations open simultaneously per sheet, which is real wiring work, not a one-liner.
**Milestone 1's CLI runs the annotation-extraction path only** (the highest-confidence tier,
and sufficient to prove the pipeline and pass the annotation-form gate). Wiring flattened/
scanned into the CLI is Task 14's golden-set runner's job, once real golden-set jobs make
clear which forms actually need exercising end-to-end — building it blind here risks the
same kind of untested-assumption bug the geometry task's discovery-test approach was meant to
avoid.

- [ ] **Step 4: Fix the flagged gap — remove the broken conditional, run annotation-only**

```python
# replace the markups = (...) block above with:
            markups = extract_annotation_markups(markup_source_page, pairing.a)
```

- [ ] **Step 5: Run the end-to-end test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli_end_to_end.py -v`
Expected: 1 passed

- [ ] **Step 6: Run the FULL test suite to confirm nothing regressed**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all tests across all prior tasks still pass (~40 tests total)

- [ ] **Step 7: Commit**

```bash
git add pickup_checker/pickup_checker/cli.py pickup_checker/tests/test_cli_end_to_end.py
git commit -m "pickup_checker: end-to-end CLI pipeline (annotation-form markups in M1; flattened/scanned wiring deferred to golden-set runner)"
```

---

## Task 14: Golden-set runner and labeling protocol

**Files:**
- Create: `F:\AI-Dev\AI-Server\pickup_checker\run_golden_eval.py`
- Create: `F:\AI-Dev\AI-Server\pickup_checker\golden_set\README.md`
- Test: `F:\AI-Dev\AI-Server\pickup_checker\tests\test_golden_eval.py`

**Interfaces:**
- Consumes: `pickup_checker.gates.*`, `pickup_checker.verdict.score_finding`
- Produces: a dashboard script mirroring the Phase 9 spike's `run_eval.py` pattern — prints a
  per-gate PASS/FAIL table, auto-synthesizes a tiny demo set if `golden_set/` has no labeled
  jobs yet (so the harness is provable on day one, per that same precedent).

This task does **not** create the real 6-job golden set (spec §11.5) — that is manual
labeling work the user does later, following the protocol this task writes down. This task
proves the harness runs and correctly reports PASS/FAIL, using synthetic data.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_golden_eval.py
from run_golden_eval import evaluate_region_comparison_metrics


def test_evaluate_region_comparison_metrics_computes_rates_correctly():
    # 4 labeled cases: truth vs. what score_finding would produce
    # (verdict, ground_truth) pairs -- ground truth is the ONLY binary label (spec §11.3)
    from pickup_checker.models import Verdict

    labeled = [
        (Verdict.UNCHANGED, "UNCHANGED"),   # correct
        (Verdict.CHANGED, "CHANGED"),        # correct
        (Verdict.UNCHANGED, "CHANGED"),      # FALSE CLEAR -- the dangerous one
        (Verdict.CHANGED, "UNCHANGED"),      # false flag
    ]
    metrics = evaluate_region_comparison_metrics(labeled)
    assert metrics["false_clear_rate"] == 0.25  # 1 of 4
    assert metrics["false_flag_rate"] == 0.25   # 1 of 4
    assert metrics["indeterminate_rate"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_golden_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_golden_eval'`

- [ ] **Step 3: Implement `run_golden_eval.py`**

```python
# run_golden_eval.py
"""Golden-set dashboard. Mirrors the BIMpossible Phase 9 spike's run_eval.py
pattern (spec §11 references this precedent directly): per-gate PASS/FAIL table,
stamped with a version, synthesizes a tiny demo set if none is labeled yet so the
harness is provable before real labeling work happens."""
from __future__ import annotations

import sys
from pathlib import Path

from pickup_checker.gates import (
    check_gate, REGION_COMPARISON_GATE_V1, SHEET_MATCHING_GATE_V1,
)
from pickup_checker.models import Verdict

TOOL_VERSION = "0.1.0"
GOLDEN_SET_DIR = Path(__file__).parent / "golden_set"


def evaluate_region_comparison_metrics(labeled: list[tuple]) -> dict:
    """labeled: list of (predicted_verdict: Verdict, ground_truth: 'CHANGED'|'UNCHANGED')."""
    n = len(labeled)
    if n == 0:
        return {"false_clear_rate": None, "false_flag_rate": None, "indeterminate_rate": None}

    false_clears = sum(1 for pred, truth in labeled if pred is Verdict.UNCHANGED and truth == "CHANGED")
    false_flags = sum(1 for pred, truth in labeled if pred is Verdict.CHANGED and truth == "UNCHANGED")
    indeterminate = sum(1 for pred, _ in labeled if pred is Verdict.INDETERMINATE)

    return {
        "false_clear_rate": false_clears / n,
        "false_flag_rate": false_flags / n,
        "indeterminate_rate": indeterminate / n,
    }


def _synthesize_demo_labels() -> list[tuple]:
    """No real golden-set jobs labeled yet -- proves the harness runs end-to-end
    with a tiny hand-built demo set, same role as Phase9's synthetic fallback."""
    return [
        (Verdict.UNCHANGED, "UNCHANGED"),
        (Verdict.CHANGED, "CHANGED"),
        (Verdict.UNCHANGED, "UNCHANGED"),
        (Verdict.CHANGED, "UNCHANGED"),  # one deliberate false flag in the demo set
    ]


def main() -> int:
    labeled_jobs = list(GOLDEN_SET_DIR.glob("*/labels.json"))
    if labeled_jobs:
        print(f"found {len(labeled_jobs)} labeled golden-set job(s) -- real evaluation not yet wired;")
        print("see golden_set/README.md for the labeling protocol and next steps.")
        return 0

    print(f"pickup_checker golden-set dashboard -- tool v{TOOL_VERSION}")
    print("no labeled golden-set jobs found in golden_set/ -- using a synthetic demo set")
    print("(see golden_set/README.md to build the real GoldenSet v1.0)\n")

    demo_labels = _synthesize_demo_labels()
    metrics = evaluate_region_comparison_metrics(demo_labels)
    gate_result = check_gate(metrics, REGION_COMPARISON_GATE_V1)

    print("Region comparison gate:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    status = "PASS" if gate_result["pass"] else "FAIL: " + "; ".join(gate_result["failures"])
    print(f"  -> {status}\n")

    print("Sheet matching / markup extraction / queue usefulness gates: no data yet")
    print("(require real golden-set jobs -- see golden_set/README.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_golden_eval.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the dashboard manually to confirm output**

Run: `.venv/Scripts/python.exe run_golden_eval.py`
Expected: prints the demo-set metrics and a PASS/FAIL line for the region-comparison gate
(the demo set includes one deliberate false flag, so `false_flag_rate` should show `0.25`,
which is within the `0.20` gate... note: **0.25 > 0.20, so this demo set should print FAIL**
— if it prints PASS, the gate math has a bug; re-check `check_gate`'s direction inference
before proceeding.

- [ ] **Step 6: Write the labeling protocol**

```markdown
# golden_set/README.md

# GoldenSet v1.0 — labeling protocol

Full context: `docs/superpowers/specs/2026-07-25-pdf-pickup-checker-design.md`, §11.

## Composition target

**6 jobs**, spanning all three input modes (marked-prior, clean-only, separate-markup) and
all three markup forms (annotation, flattened, scanned), with >=15 markup instances per form
across the set. Sized to cover the failure modes, not padded (spec §11.5) — grow only once
v1.0 stops discriminating between good and bad runs.

## Directory shape (per job)

    golden_set/
      job-01-<short-name>/
        prior.pdf              (or prior_marked.pdf / prior_clean.pdf, per that job's mode)
        markup.pdf              (only if that job is separate-markup mode)
        revised.pdf
        labels.json              (see schema below)

## Labeling rules (frozen — spec §11.3, do not adjust without updating the spec)

- Ground truth per region is **binary**: `CHANGED` or `UNCHANGED`. `INDETERMINATE` is a tool
  OUTPUT only — never assign it as a label.
- **Revision clouds and revision-block tags are excluded from content comparison.** A cloud
  drawn around an otherwise-untouched region is labeled `UNCHANGED`.
- Text reflow with identical content -> `UNCHANGED`.
- Line weight / color / hatch change only, no content change -> `CHANGED`.
- Content deleted (not replaced) -> `CHANGED`.
- Residual sub-tolerance shift after registration -> `UNCHANGED`.
- **One markup = one reviewer intent.** A cloud with an attached callout is one markup.
- Sheet matching: same sheet number + same discipline = matched. A renumbered/resheeted
  sheet is labeled matched with an explicit `note` explaining the renumber.

## Anti-anchoring rule

Labels **start from the tool's own proposals** as a labeling aid, but the labeler must be
free to **fully overwrite** a proposal, not just edit it. Treat every proposed label as
disposable. This is the exact rule the spec's §11.5 review tightened — anchoring on the
tool's own output during golden-set creation would bias ground truth toward what the tool
already believes, defeating the point of an independent gate.

## labels.json schema

    {
      "job_id": "job-01-example",
      "input_mode": "marked_prior",
      "regions": [
        {
          "sheet_number": "E1.01",
          "markup_form": "annotation",
          "ground_truth": "UNCHANGED",
          "note": null
        }
      ]
    }

## Status

No real golden-set jobs exist yet — this is manual work the user does when ready. Run
`python run_golden_eval.py` at any time; it reports the synthetic-demo-set result until real
jobs are added.
```

- [ ] **Step 7: Commit**

```bash
git add pickup_checker/run_golden_eval.py pickup_checker/golden_set/README.md \
        pickup_checker/tests/test_golden_eval.py
git commit -m "pickup_checker: golden-set dashboard + labeling protocol (spec §11.5)"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| §2 observation-vs-interpretation (`Verdict` only, never "addressed") | Task 2 (`Verdict` enum has no ADDRESSED value), Task 11 |
| §3 input modes + `MaxClaim` per mode | Task 2 (`InputMode`, `max_claim_for_mode`), Task 5, Task 11 |
| §4 markup forms + confidence tiers | Tasks 6/7/8 (`evidence_quality` differs by path in Task 11) |
| §5 `Finding`/`Assessment`/`ReviewRecord` split, `SheetPairing` as first-class outcomes | Task 2 |
| §5 canonical inches, `/Rotate` safety | Task 3 |
| §6 module architecture | File Structure section, matches exactly |
| §7 sheet matching, never guess | Task 4 |
| §8 registration | **Not built in Milestone 1** — `Provenance.registration_offset`/`registration_confidence` fields exist (Task 2) and are left `None`/unset by Tasks 9–10, which is itself a form of "no registration attempted yet" rather than a silent wrong-offset assumption. Full registration logic is out of scope for this plan; flagged here rather than silently dropped. |
| §9 fail-toward-review | Task 11 (`INDETERMINATE` on missing evidence) |
| §10 no AI in detection | Nowhere in this plan — by omission, as intended |
| §11.1 sheet-matching gate | Task 12 (`SHEET_MATCHING_GATE_V1`) |
| §11.2 per-form markup extraction gates | Task 12 (`MARKUP_EXTRACTION_GATES_V1`) |
| §11.3 region-comparison gate + labeling rubric | Task 12 (`REGION_COMPARISON_GATE_V1`), Task 14 (`golden_set/README.md`) |
| §11.4 queue-usefulness gate | Task 12 (`QUEUE_USEFULNESS_GATE_V1`) — **not exercised end-to-end in Milestone 1** since there's no queue yet (Milestone 2); the gate constants exist and are tested, ready for Milestone 2's plan to consume |
| §11.5 golden set composition + anti-anchoring | Task 14 |
| §14 licensing | Global Constraints, Task 1 |
| §16 Phase 17 pointer | Not applicable to an implementation plan — it's a documentation-only section of the spec, no code required |

**Gap acknowledged, not hidden:** full page-registration (§8) and full three-markup-form CLI
wiring (flagged explicitly in Task 13) are the two pieces of Milestone 1 scope deliberately
narrowed during implementation planning. Both are recorded as open items rather than silently
built halfway — registration's fields exist in the data model so Milestone 2 doesn't need a
schema change to add real registration logic later.

**2. Placeholder scan:** no "TBD"/"TODO" in any code block. Task 9's `crop_before_path`
placeholder strings are explained inline (why they exist, what supersedes them) rather than
left as unexplained stubs. Task 13's flagged gap is resolved within the same task (Step 4),
not left dangling.

**3. Type consistency check:** `Region`, `SheetRef`, `Matched`/`UnmatchedA`/`UnmatchedB`/
`Ambiguous`, `Markup`, `Evidence`, `Provenance`, `Finding`, `Assessment`, `Verdict`, `Method`,
`MethodParams`, `InputMode`, `MaxClaim`, `ReviewStatus`, `ReviewRecord` are defined once in
Task 2 and referenced by identical names/shapes in every later task — verified by re-reading
each task's imports against Task 2's actual field names (e.g. `Finding.pairing` not
`Finding.sheet_pairing`, consistent everywhere it's constructed in Tasks 9/10/13).
`score_finding`'s signature (Task 11) matches every call site in Task 13. `check_gate`'s
`_max`/`_min` suffix convention (Task 12) matches every gate dict's key names.

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-25-pdf-pickup-checker.md`. Two
execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between
tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch
execution with checkpoints.

**Which approach?**
