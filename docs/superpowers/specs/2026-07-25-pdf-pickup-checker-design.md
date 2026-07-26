# PDF Pickup Checker — Design Spec

**Status:** approved design, pre-implementation
**Date:** 2026-07-25
**Home:** standalone tool in `F:\AI-Dev\AI-Server` (this repo), Python
**Secondary deliverable:** a Phase 17 adoption plan for BIMpossible (§12) — not a build, a pointer for later

---

## 1. Problem

After a redline review pass, drawings get reissued with pickups applied. The manual QA step —
"did every markup actually get addressed?" — is slow and error-prone at real sheet counts
(a full permit set can run 400+ sheets).

**This is not "diff two PDFs."** Full-sheet diffing floods the reviewer with every revision
cloud, date bump, and text reflow, which is how these tools become noise nobody trusts. The
actual question is narrower and harder: *for each thing someone asked to be changed, was it
changed?* That requires the markups themselves as an input, not just two drawing revisions.

## 2. Core principle: observation vs. interpretation

The tool makes exactly one kind of claim with confidence: **"this region did or did not
change."** That is observable and deterministic.

It never claims **"this redline was addressed."** Whether a change satisfies a reviewer's
intent is a judgment call a human makes. A tool that blurs this line produces false
confidence, which is worse than producing no tool at all.

This is enforced in the data model (§5), not left as a documentation aside.

**Future extension, explicitly not in v1:** a narrow, mechanically-verifiable subset of
"addressed" may be definable later — e.g., exact text replacement fully inside an annotated
box, where "changed" and "addressed" genuinely coincide. This is a possible future addition,
not a v1 feature, and must not be inferred by default in any later work on this tool.

## 3. Input modes

The tool accepts any combination of three input shapes. **What it's allowed to claim differs
by mode, and this is enforced in code via `MaxClaim` (§5), not by convention.**

| Mode | Inputs | Max claim |
|---|---|---|
| 1 | prior issue **with markups** + revised issue | `markup region changed` / `unchanged` |
| 2 | clean prior issue + revised issue (no markup file) | `region changed` — **never** anything about pickups |
| 3 | clean prior + separate markup file + revised issue | `markup region changed` / `unchanged`, cleanest markup isolation |

Mode 2 cannot know what was supposed to change, so it cannot report a missed pickup. The
`Finding.max_claim` field makes this a structural property of every finding, not a UI label
that can be forgotten.

## 4. Markup forms and confidence tiers

Markups arrive in three forms, each with a different detection method and an inherent
confidence ceiling:

| Form | Detection | Confidence tier |
|---|---|---|
| Bluebeam/Acrobat annotation objects | Structural: exact coords, author, date, comment text | High |
| Flattened into the page | Visual: color/shape heuristics | Medium |
| Scanned paper markup | Raster: deskew + ink detection | Low |

Confidence tier feeds `Assessment.evidence_quality` (§5); it does not gate whether a finding
is produced, only how much weight it carries in ranking.

## 5. Data model

Three objects with different lifecycles. Conflating them was an early design mistake caught
during review — an immutable evidence record, a derived judgment, and mutable review state
do not belong in one class.

```python
class MaxClaim(Enum):
    REGION_CHANGED = "region_changed"    # mode 2 ceiling: "changed" only, no markup context
    MARKUP_STATUS_ONLY = "markup_status"  # mode 1/3 ceiling: "markup region changed/unchanged" — "addressed" is never claimed, in either mode

class Verdict(Enum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    INDETERMINATE = "indeterminate"   # tool punts; scored as abstain, never as wrong

class Method(Enum):
    TEXT_DIFF = "text_diff"           # pdfplumber word-level comparison, vector path
    RASTER_DIFF = "raster_diff"       # pixel comparison, scanned/flattened fallback
    ANNOTATION_STRUCTURAL = "annotation_structural"

@dataclass(frozen=True)
class MethodParams:
    method: Method
    params: dict            # e.g. {"dpi": 300} or {"text_similarity_threshold": 0.9}

@dataclass(frozen=True)
class SheetRef:
    document_id: str
    page_index: int
    sheet_number: str | None   # parsed from title block; None if unparseable

# First-class outcome, not a sentinel hiding inside SheetRef
SheetPairing = (
      Matched(a: SheetRef, b: SheetRef, note: str | None)   # note: e.g. "resheeted, matched by number"
    | UnmatchedA(a: SheetRef)   # present in prior, absent in revised
    | UnmatchedB(b: SheetRef)   # present in revised, absent in prior
    | Ambiguous(candidates: list[tuple[SheetRef, SheetRef]])  # routed to review, never guessed
)

@dataclass(frozen=True)
class Region:
    # canonical space: PHYSICAL INCHES from the top-left of the UNROTATED page.
    # Not pixels (DPI varies between documents), not raw PDF points pre-transform
    # (a page carrying /Rotate 90 has swapped rect/mediabox and coordinates from
    # search_for()-style calls are in unrotated space — this bit a real PyMuPDF
    # script during the Revit-OCR evaluation and is not a hypothetical risk).
    x0: float; y0: float; x1: float; y1: float

@dataclass(frozen=True)
class Markup:
    id: str
    sheet: SheetRef
    region: Region
    form: Literal["annotation", "flattened", "scanned"]
    author: str | None
    comment_text: str | None
    source_page_rotation_applied: int   # degrees; documents the transform, always recorded

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
    """Immutable evidence. Never mutated after creation."""
    id: str
    pairing: SheetPairing
    markup: Markup | None          # None only possible when max_claim == REGION_CHANGED (mode 2)
    region: Region
    method: MethodParams
    evidence: Evidence
    provenance: Provenance

@dataclass(frozen=True)
class Assessment:
    """Derived judgment about a Finding. Separate from Finding so re-scoring
    (e.g. after a threshold recalibration) never requires re-extracting evidence."""
    finding_id: str
    verdict: Verdict
    suspicion_score: float      # ranks queue priority — how likely this is a missed pickup
    evidence_quality: float     # confidence in the observation itself (independent axis)
    max_claim: MaxClaim

class ReviewStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"     # human agrees this needs action / is a real miss
    DISMISSED = "dismissed"     # human reviewed, no action needed

@dataclass
class ReviewRecord:
    """Mutable. The only object that changes after creation."""
    finding_id: str
    status: ReviewStatus
    reviewer: str | None
    decision_note: str | None
    created_at: datetime
    resolved_at: datetime | None
```

**Queue sort order** (primary → tiebreak):

1. `verdict == UNCHANGED` first — an unaddressed markup is the target signal
2. `verdict == INDETERMINATE` next — uncertain, needs a human look
3. higher `suspicion_score`
4. higher `evidence_quality`
5. sheet order (stable, for reproducible review sessions)

`verdict == CHANGED` sorts last: the markup was likely addressed, lowest review priority.

## 6. Architecture

```
ingest.py     load documents, detect input mode from what's provided
sheets.py     pair pages across documents -> SheetPairing
geometry.py   canonical coordinate space + registration (handles /Rotate, DPI, page-size diffs)
markups/
  annotations.py   structural extraction from PDF annotation objects
  flattened.py     color/shape heuristic detection
  scanned.py       deskew + ink detection
compare.py    region comparison: text-first (pdfplumber), raster fallback -> Finding
verdict.py    PURE. Finding -> Assessment. No I/O, no PDF library import. Scoring + gate logic only.
queue.py      SQLite-backed ReviewRecord store
report.py     annotated-PDF export (reportlab) — writes real PDF annotations onto doc B
```

`verdict.py` being pure, dependency-free, and I/O-free is what makes the gate harness (§11)
runnable against fixtures with no PDF parsing involved — mirrors the Phase 9 spike's
`evaluate.py` pattern in the BIMpossible workspace, which proved out exactly this shape.

**Region comparison is text-first.** These are vector PDFs with a real text layer; comparing
extracted words + coordinates via pdfplumber is far cheaper and more precise than pixel
diffing. Raster comparison is the fallback for scanned input and graphics-only changes
(line weight, hatching) where there's no text to compare.

**No AI anywhere in detection.** Detection, scoring, and queue ranking are 100% deterministic.
See §10 for why an AI explainer is excluded even from being an option in v1.

## 7. Sheet matching

Extract sheet number from the text layer by regex (e.g. `E1.01`, `A-101`), weighted toward
the title-block region, with page-order proximity as a tiebreaker. Page counts differ between
issues in practice (sheets added/dropped) — this is expected, not an error condition.

- Confident match on sheet number + discipline → `Matched`, with a `note` if the match
  required inference (e.g. a resheet).
- No candidate on the other side → `UnmatchedA` / `UnmatchedB`, surfaced explicitly, never
  silently dropped from the run.
- Multiple plausible candidates → `Ambiguous`, routed to review. **Never guessed.**

**`Finding` objects are only produced for `Matched` pairings.** `UnmatchedA`/`UnmatchedB`/
`Ambiguous` are reported as their own run-level outcomes — a sheet that couldn't be paired
has nothing to compare, so it cannot generate comparison evidence. It still surfaces to the
reviewer, just not as a `Finding`.

## 8. Registration

Vector documents: align via common text-anchor matching, compute a physical-unit offset.
Scanned documents: feature-based image alignment. A registration failure is an explicit
outcome (`Provenance.registration_confidence` low or absent) that pushes the resulting
finding toward `INDETERMINATE` — never silently treated as zero offset.

## 9. Error-handling posture: fail toward review

A false `UNCHANGED`-when-verdict-should-be-CHANGED (a **false clear**) deletes a real missed
pickup from the reviewer's attention, because `UNCHANGED` sorts first and reads as "handled."
A false `CHANGED`-when-should-be-UNCHANGED (a **false flag**) costs the reviewer thirty
seconds. These are not symmetric costs, and the gates in §11 encode that asymmetry directly
rather than leaving it as a design aspiration.

Any comparison with material uncertainty — failed registration, raster-only region, shaky
markup detection — resolves to `INDETERMINATE`, which is visible in the queue. Uncertainty
never silently resolves toward `CHANGED`, because that would remove the item from view.

## 10. What's excluded from v1, deliberately

- **No AI explainer.** Even flag-gated and default-off, it's excluded from milestone 1
  entirely (§13) — introducing it before detection and the queue are independently trusted
  would make debugging false clears/flags ambiguous ("is this a detection bug or a summary
  bug?"). It may be added after v1 ships, strictly downstream of findings, never able to
  create/rank/suppress a finding.
- **No mechanical "addressed" verdict** — see §2's future-extension note.
- **No Revit writes, no APS calls.** Purely reads locally-supplied PDFs.

## 11. Golden set and gates

Four **independent** gates. Collapsing them into one score would hide which stage failed —
matching, extraction, comparison, and end-to-end usefulness fail for unrelated reasons.

**Gate numbers freeze before the first real run against the golden set.** Adjusting them
after seeing results is moving the goalposts and defeats the purpose of having them.

**Ship gate:** this tool does not get ported into BIMpossible (§12) until it passes all four
gates on GoldenSet v1.0.

### 11.1 Sheet matching

| metric | direction | v1.0 |
|---|---|---|
| `false_match_rate` (wrongly paired sheets) | max | **0.00** |
| `match_recall` | min | 0.95 |
| `unmatched_rate` | max | 0.10 |

Zero false matches is deliberate: an unmatched sheet is a visible review item; a *wrongly*
matched sheet silently corrupts every finding built on it while looking plausible.

### 11.2 Markup extraction — gated per form, never pooled

Pooling would let a near-perfect annotation score mask a weak scanned score.

| form | `recall_min` | `precision_min` | `bbox_iou_min` |
|---|---|---|---|
| annotation | 0.99 | 0.99 | 0.95 |
| flattened | 0.85 | 0.80 | 0.70 |
| scanned | 0.70 | 0.70 | 0.60 |

Scanned is expected to fail this gate at v1.0. That is the correct outcome — it means
scanned input is not yet trusted, not that the gate is miscalibrated.

**Markup unit rubric:** one markup = one reviewer intent. A cloud with an attached callout
is one markup, not two. Loose ink scribbles within one bounding box and one apparent
gesture are one markup.

### 11.3 Region comparison

| metric | meaning | direction | v1.0 |
|---|---|---|---|
| `false_clear_rate` | tool said UNCHANGED when ground truth is CHANGED | max | **0.01** |
| `false_flag_rate` | tool said CHANGED when ground truth is UNCHANGED | max | 0.20 |
| `indeterminate_rate` | punted to review | max | 0.25 |

`false_clear_rate` gets the tight bound: it is the metric for the dangerous failure (§9).
`false_flag_rate` gets a 20x looser bound because its cost is only review time.

**Labeling rubric (ground truth is binary — CHANGED or UNCHANGED; `INDETERMINATE` is a tool
output only, scored as an abstain, never as wrong, matching the Phase 9 spike's treatment of
abstains):**

- Revision clouds and revision-block tags are **excluded from content comparison** — they
  are metadata *about* a change, not the change itself. A cloud drawn around an otherwise
  untouched region is `UNCHANGED`. (Without this rule, every picked-up sheet trivially
  self-certifies as changed via its own revision cloud.)
- Text reflow with identical content → `UNCHANGED`
- Line weight / color / hatch change only, no content change → `CHANGED`
- Content deleted (not replaced) → `CHANGED`
- Residual sub-tolerance shift after registration → `UNCHANGED`

### 11.4 Queue usefulness — end to end

| metric | direction | v1.0 |
|---|---|---|
| `recall_at_full_queue` | min | **1.00** |
| `recall_at_10` | min | 0.80 |
| `mean_reciprocal_rank` | min | 0.50 |
| `precision_at_10` | min | 0.50 |
| `items_per_sheet` | max | 15 |

`recall_at_full_queue = 1.00`: every known missed pickup in the golden set must appear
*somewhere* in the queue — a tool that misses a real miss is worse than no tool. The
rank-aware metrics (`recall_at_10`, MRR) exist because recall alone is satisfied even if the
real miss is buried at position 147; that technically passes recall while failing the actual
product goal of a scannable queue.

### 11.5 Golden set composition

**6 jobs** (sized to cover the failure modes, not padded) spanning all three input modes and
all three markup forms, with ≥15 markup instances per form. Labels built by correcting the
tool's own proposals (per-field/per-region), reviewed by a human, versioned as `v1.0`. Grow
the set only once v1.0 stops discriminating between good and bad runs.

**Sheet-matching rubric:** same sheet number + same discipline = matched. A renumbered/
resheeted sheet is labeled matched with an explicit `note`, so the matcher isn't penalized
for a real-world renumber it had no way to detect from content alone.

## 12. Testing strategy

- `verdict.py` (pure): unit tests against synthetic `Finding` fixtures — no PDF files
  involved. This is the fast, deterministic core and should have the tightest coverage.
- `sheets.py`, `geometry.py`: unit tests with synthetic coordinate/rotation cases, explicitly
  including a `/Rotate 90` fixture (this exact bug already cost real time once).
- `markups/*`: one test module per form, using small real-world-shaped fixture PDFs (not
  full sheets) — annotation objects, flattened color regions, scanned ink.
- `compare.py`: golden-set-driven, per §11.3's labeling rubric.
- End-to-end: the golden-set runner IS the integration test — same role as Phase 9's
  `run_eval.py`, producing a per-gate PASS/FAIL table stamped with a tool version.
- No database required for `verdict.py`'s test lane — mirrors the BIMpossible backend CI's
  "pure lane" pattern (tests that must pass with zero external services).

## 13. Milestones

1. **Detection core.** `ingest → sheets → geometry → markups → compare → verdict`, driven
   entirely by the CLI + golden-set runner. No queue persistence, no UI. Ships when all four
   gates pass on GoldenSet v1.0.
2. **Review queue.** SQLite-backed `ReviewRecord`, local web UI (list + region crops +
   confirm/dismiss), sorted per §5.
3. **PDF export.** Annotated-PDF output via reportlab — confirmed findings become real
   annotations on a copy of the revised issue, for opening in Bluebeam/Acrobat.

**No AI explainer in milestone 1, full stop** (§10) — not flagged off, simply not present,
so nothing about detection or queue trust can be attributed to it.

## 14. Licensing

No PyMuPDF (`fitz`) anywhere in this tool, even though AGPL doesn't legally bind a personal
local tool — BIMpossible's backend hard-bans it (removed 2026-06-04, verified by audit), and
building on it now would make §12's Phase 17 port a rewrite instead of a port.

| library | license | role |
|---|---|---|
| `pdfplumber` | MIT | text/word extraction, primary comparison path |
| `pypdfium2` | Apache-2.0 / BSD-3 | rasterization for scanned/flattened fallback |
| `reportlab` | BSD | annotated-PDF export |

This matches BIMpossible's already-approved set exactly (`pdfplumber` was ratified by the
Phase 9 spike; `reportlab` is already in the BIMpossible backend).

## 15. Environment note

Runs on the same box as the local Ollama/opencode setup. If a future AI explainer is added
per §10, it must use the OpenAI-compatible endpoint only (`/v1/chat/completions`), never
shell out to the `ollama` CLI, per AI-Server's existing runtime-agnostic rule. The detection
core in v1 has no model dependency at all.

## 16. Phase 17 adoption notes (BIMpossible) — pointer only, not a build

This tool is built standalone here. If BIMpossible later adopts it, per the workspace's
roadmap-hygiene rules this requires, at minimum:

- A new Phase number (17+; numbers are frozen once assigned, never reassigned) with its own
  `Phase17_BuildSpec.md` in `00_Strategy/` and a `PHASE-STATUS.md` row.
- A prior-art research pass before scope-lock (workspace standing rule for any new capability).
- Porting `queue.py` from SQLite to the backend's Postgres/SQLAlchemy/Alembic stack, as a new
  `backend/` package (likely alongside `aec/`, per the routers-own-policy /
  reusable-mechanics-in-services layering rule) — not a new top-level `tools/` entry, which
  isn't a feature convention in that repo.
- A feature flag default-OFF, following the `revit_link/feature_flag.py` pattern: one
  predicate per capability (read vs. write vs. export, each independently toggleable), named
  `BIMPOSSIBLE_<AREA>_<CAP>_ENABLED`.
- Resolving the open Phase 5.2 design question this brushes against: whether BIMpossible PDF
  outputs are informational or submission-grade (submission-grade would require an audit
  stamp, version lock, and "data as of" provenance on any exported annotated PDF).
- §11's ship gate already applies: gates must pass on GoldenSet v1.0 *before* this port is
  even proposed, regardless of BIMpossible's own process.
- Licensing (§14) is already Phase-17-compatible by construction — this is the one porting
  step already done.

No BIMpossible roadmap document is modified by this spec. This section exists so a future
session has a concrete starting point rather than rediscovering these constraints.
