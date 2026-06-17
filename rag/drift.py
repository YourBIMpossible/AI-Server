"""Drift: surface decisions that aren't reflected in the canonical docs.

For each decision-log entry we find its closest chunk among the *canonical* docs (the index,
minus the decision-log itself). A decision whose best match is weak -- or has no match at all
-- is a candidate undocumented decision. Output: out/rag/drift-YYYY-MM-DD.md.

CLI:  python -m rag.drift          # uses WORKSPACE/AI-Brain-Data/decision-log
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, get_logger, load_config

from .store import VectorStore

Embedder = Callable[[list[str]], list[list[float]]]
DEFAULT_THRESHOLD = 1.0  # L2 on unit vectors; above this = "no strong canonical match"
_MAX_EMBED_CHARS = 8000  # keep a long decision entry within the embed model's context window


@dataclass
class DriftItem:
    decision_path: str
    best_match_path: str | None
    best_distance: float | None


def analyze(
    decision_root: Path,
    store: VectorStore,
    embedder: Embedder,
    *,
    exclude_prefixes: tuple[str, ...] = (),
) -> list[DriftItem]:
    items: list[DriftItem] = []
    for f in sorted(decision_root.rglob("*.md")):
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")[:_MAX_EMBED_CHARS]
        vec = embedder([text])[0]
        hits = store.knn(vec, k=1, exclude_prefixes=exclude_prefixes)
        if hits:
            items.append(DriftItem(str(f), hits[0].path, hits[0].distance))
        else:
            items.append(DriftItem(str(f), None, None))
    return items


def flag(items: list[DriftItem], threshold: float) -> list[DriftItem]:
    return [it for it in items if it.best_distance is None or it.best_distance > threshold]


def write_report(
    items: list[DriftItem], threshold: float, out_dir: Path, today: str
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    flagged = flag(items, threshold)
    lines = [
        f"# Decision drift — {today}",
        "",
        f"_{len(flagged)} of {len(items)} decisions have no strong match in the canonical docs "
        f"(L2 threshold {threshold:.3f})._",
        "",
    ]
    if not flagged:
        lines.append("No drift: every decision maps to a canonical doc.")
    else:
        lines.append("## Candidate undocumented decisions")
        lines.append("")
        for it in flagged:
            if it.best_match_path is None:
                lines.append(f"- **{it.decision_path}** — no match in the index")
            else:
                lines.append(
                    f"- **{it.decision_path}** — weak match: {it.best_match_path} "
                    f"(distance {it.best_distance:.3f})"
                )
    report = out_dir / f"drift-{today}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    cfg = load_config()
    log = get_logger("rag-drift")
    decision_root = cfg.workspace / "AI-Brain-Data" / "decision-log"
    if not decision_root.exists():
        print(f"[FAIL] decision-log not found: {decision_root}", file=sys.stderr)
        return 1

    store = VectorStore(cfg.out / "rag" / "index.db")
    items = analyze(
        decision_root, store, LLM(cfg).embed, exclude_prefixes=(str(decision_root),)
    )
    store.close()
    today = datetime.now().strftime("%Y-%m-%d")
    report = write_report(items, DEFAULT_THRESHOLD, cfg.out / "rag", today)
    log("drift", decisions=len(items), flagged=len(flag(items, DEFAULT_THRESHOLD)), report=str(report))
    print(f"[OK] Wrote {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
