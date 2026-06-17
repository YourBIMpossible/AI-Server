"""Ingest: walk configured source roots, chunk + embed markdown, upsert into the store.

Incremental: a file is re-embedded only when its mtime changed AND its content hash
differs; mtime-only drift just updates the recorded mtime. Files removed from disk are
dropped from the index. Read-only on sources; the index lives under out/rag/.

CLI:  python -m rag.ingest          # index the roots in config/rag_sources.txt
"""
from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, get_logger, load_config

from .chunk import chunk_markdown

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = REPO_ROOT / "config" / "rag_sources.txt"

Embedder = Callable[[list[str]], list[list[float]]]
_SKIP_PARTS = {".git", "__pycache__", ".obsidian", ".pytest_cache", "out"}


@dataclass
class Report:
    new: int = 0
    changed: int = 0
    removed: int = 0
    unchanged: int = 0
    chunks_indexed: int = 0


def read_sources(config_path: Path = DEFAULT_SOURCES) -> list[Path]:
    """Parse one-path-per-line source roots ('#' lines and blanks ignored)."""
    if not config_path.exists():
        return []
    roots: list[Path] = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            roots.append(Path(line))
    return roots


def iter_source_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.md")):
            if p.is_file() and not any(part in _SKIP_PARTS or part.startswith(".") for part in p.parts):
                yield p.resolve()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ingest(
    roots: Iterable[Path],
    store,
    embedder: Embedder,
    *,
    chunker: Callable[[str], list] = chunk_markdown,
) -> Report:
    report = Report()
    disk = {str(p): p for p in iter_source_files(roots)}

    for stale in set(store.indexed_paths()) - set(disk):
        store.delete_file(stale)
        report.removed += 1

    for key, path in disk.items():
        mtime = path.stat().st_mtime
        state = store.file_state(key)
        if state and state[0] == mtime:
            report.unchanged += 1
            continue
        h = file_hash(path)
        if state and state[1] == h:
            store.touch(key, mtime)  # content identical, mtime drifted only
            report.unchanged += 1
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = chunker(text)
        embeddings = embedder([c.text for c in chunks]) if chunks else []
        store.upsert_file(
            key, mtime, h, [(c.heading, c.text, e) for c, e in zip(chunks, embeddings)]
        )
        report.chunks_indexed += len(chunks)
        if state:
            report.changed += 1
        else:
            report.new += 1

    return report


def main() -> int:
    cfg = load_config()
    log = get_logger("rag-ingest")
    roots = read_sources()
    if not roots:
        print(f"[FAIL] No sources in {DEFAULT_SOURCES}", file=sys.stderr)
        return 1
    from .store import VectorStore

    store = VectorStore(cfg.out / "rag" / "index.db")
    report = ingest(roots, store, LLM(cfg).embed)
    store.close()
    log(
        "ingest",
        new=report.new,
        changed=report.changed,
        removed=report.removed,
        unchanged=report.unchanged,
        chunks=report.chunks_indexed,
    )
    print(
        f"[OK] ingest: +{report.new} new, ~{report.changed} changed, "
        f"-{report.removed} removed, {report.unchanged} unchanged "
        f"({report.chunks_indexed} chunks embedded)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
