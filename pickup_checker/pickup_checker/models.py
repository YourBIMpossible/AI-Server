"""All data types for pickup_checker. Zero PDF-library imports -- keeps this
module (and verdict.py, which depends only on this) importable and testable
with no PDF parsing involved."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Union


class InputMode(Enum):
    """Which combination of documents a run was given. Spec section 3."""
    MARKED_PRIOR = "marked_prior"        # mode 1: prior WITH markups + revised
    CLEAN_ONLY = "clean_only"            # mode 2: clean prior + revised, no markup file
    SEPARATE_MARKUP = "separate_markup"  # mode 3: clean prior + markup file + revised


class MaxClaim(Enum):
    REGION_CHANGED = "region_changed"     # mode 2 ceiling: "changed" only
    MARKUP_STATUS_ONLY = "markup_status"  # mode 1/3 ceiling: "changed/unchanged" -- never "addressed"


def max_claim_for_mode(mode: InputMode) -> MaxClaim:
    """Run-level mapping, applied uniformly by verdict.py to every Assessment in a
    run. See the plan's Task 2 design note for why this isn't a per-Finding check."""
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
    """Canonical space: physical INCHES from the top-left of the UNROTATED page."""
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
    when the run's InputMode is CLEAN_ONLY."""
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
