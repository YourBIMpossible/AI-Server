"""WP-B ingest: walk sources, embed, upsert into the store, incrementally."""
import os
from pathlib import Path

import pytest

from aiserver import LLM, load_config
from rag.ingest import ingest, read_sources
from rag.store import VectorStore

REPO = Path(__file__).resolve().parent.parent


def _embedder(url):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"OLLAMA_HOST": url})
    return LLM(cfg, retries=0).embed


def _bump_mtime(path: Path) -> None:
    t = path.stat().st_mtime + 10
    os.utime(path, (t, t))


def test_fresh_then_incremental(embed_endpoint, tmp_path):
    root = tmp_path / "vault"
    (root / "sub").mkdir(parents=True)
    f1 = root / "one.md"
    f2 = root / "sub" / "two.md"
    f1.write_text("# A\n\nalpha alpha\n", encoding="utf-8")
    f2.write_text("# B\n\nbeta\n", encoding="utf-8")

    store = VectorStore(tmp_path / "idx.db")
    embed = _embedder(embed_endpoint)

    r1 = ingest([root], store, embed)
    assert (r1.new, r1.changed, r1.removed) == (2, 0, 0)
    assert r1.chunks_indexed == 2

    r2 = ingest([root], store, embed)
    assert (r2.new, r2.changed, r2.removed, r2.unchanged) == (0, 0, 0, 2)

    f1.write_text("# A\n\nalpha alpha gamma\n", encoding="utf-8")
    _bump_mtime(f1)
    r3 = ingest([root], store, embed)
    assert (r3.new, r3.changed, r3.removed) == (0, 1, 0)

    f2.unlink()
    r4 = ingest([root], store, embed)
    assert (r4.new, r4.changed, r4.removed) == (0, 0, 1)
    assert set(store.indexed_paths()) == {str(f1.resolve())}


def test_mtime_preserving_content_change_is_still_reindexed(embed_endpoint, tmp_path):
    # RAG-2: a restore/copy that preserves mtime but changes content must not be
    # silently treated as unchanged -- the hash, not mtime, is authoritative.
    root = tmp_path / "vault"
    root.mkdir()
    f = root / "one.md"
    f.write_text("# A\n\nalpha\n", encoding="utf-8")
    store = VectorStore(tmp_path / "idx.db")
    embed = _embedder(embed_endpoint)

    ingest([root], store, embed)
    original_mtime = f.stat().st_mtime

    f.write_text("# A\n\ncompletely different content\n", encoding="utf-8")
    os.utime(f, (original_mtime, original_mtime))  # force mtime back to its old value

    r = ingest([root], store, embed)
    assert (r.new, r.changed, r.removed, r.unchanged) == (0, 1, 0, 0)


def test_mtime_drift_without_content_change_is_not_reindexed(embed_endpoint, tmp_path):
    root = tmp_path / "v"
    root.mkdir()
    f = root / "a.md"
    f.write_text("# A\n\nalpha\n", encoding="utf-8")
    store = VectorStore(tmp_path / "idx.db")
    embed = _embedder(embed_endpoint)

    ingest([root], store, embed)
    _bump_mtime(f)  # touch only; content identical
    r = ingest([root], store, embed)
    assert (r.new, r.changed, r.removed, r.unchanged) == (0, 0, 0, 1)


def test_read_sources_parses_config(tmp_path):
    cfg = tmp_path / "rag_sources.txt"
    cfg.write_text(
        "# comment\n\nF:\\AI-Dev\\AI-Brain-Data\n  F:\\AI-Dev\\BIMpossible_Workspace  \n",
        encoding="utf-8",
    )
    roots = read_sources(cfg)
    assert [str(p) for p in roots] == [
        "F:\\AI-Dev\\AI-Brain-Data",
        "F:\\AI-Dev\\BIMpossible_Workspace",
    ]


def test_missing_source_root_is_skipped_not_fatal(embed_endpoint, tmp_path):
    store = VectorStore(tmp_path / "idx.db")
    embed = _embedder(embed_endpoint)
    r = ingest([tmp_path / "does-not-exist"], store, embed)
    assert (r.new, r.changed, r.removed) == (0, 0, 0)


def test_short_embedding_response_raises_instead_of_silently_truncating(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("# A\n\nalpha beta gamma\n", encoding="utf-8")
    store = VectorStore(tmp_path / "idx.db")

    def short_embedder(texts):
        return [[0.0, 0.0]] * max(0, len(texts) - 1)  # always one short

    with pytest.raises(ValueError):
        ingest([root], store, short_embedder)
