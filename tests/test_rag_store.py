"""WP-B vector store (sqlite-vec): upsert chunks, KNN search, incremental file state."""
from rag.store import VectorStore


def _chunks():
    return [
        ("Sec1", "alpha", [1.0, 0.0, 0.0]),
        ("Sec2", "beta", [0.0, 1.0, 0.0]),
    ]


def test_knn_returns_nearest_chunk(tmp_path):
    store = VectorStore(tmp_path / "index.db")
    store.upsert_file("a.md", mtime=1.0, content_hash="h1", chunks=_chunks())
    store.upsert_file("b.md", mtime=1.0, content_hash="h2", chunks=[("X", "gamma", [0.0, 0.0, 1.0])])

    hits = store.knn([0.9, 0.1, 0.0], k=1)
    assert len(hits) == 1
    assert hits[0].path == "a.md"
    assert hits[0].heading == "Sec1"
    assert hits[0].text == "alpha"
    store.close()


def test_persisted_dim_survives_reopen(tmp_path):
    db = tmp_path / "index.db"
    VectorStore(db).upsert_file("a.md", 1.0, "h", [("S", "x", [1.0, 0.0, 0.0])])
    reopened = VectorStore(db)  # must read dim back, no re-declare error
    hits = reopened.knn([1.0, 0.0, 0.0], k=1)
    assert hits[0].path == "a.md"


def test_file_state_and_incremental_ops(tmp_path):
    store = VectorStore(tmp_path / "i.db")
    store.upsert_file("a.md", 1.0, "h1", _chunks())
    assert store.file_state("a.md") == (1.0, "h1")
    assert store.file_state("missing.md") is None
    assert set(store.indexed_paths()) == {"a.md"}

    # re-upsert replaces (no duplicate chunks)
    store.upsert_file("a.md", 2.0, "h2", [("Only", "zeta", [0.0, 0.0, 1.0])])
    assert store.file_state("a.md") == (2.0, "h2")
    assert len(store.knn([0.0, 0.0, 1.0], k=5)) == 1

    store.touch("a.md", 9.0)
    assert store.file_state("a.md") == (9.0, "h2")

    store.delete_file("a.md")
    assert store.file_state("a.md") is None
    assert store.knn([1.0, 0.0, 0.0], k=5) == []


def test_knn_can_exclude_path_prefixes(tmp_path):
    store = VectorStore(tmp_path / "i.db")
    store.upsert_file("canon/doc.md", 1.0, "h", [("C", "alpha", [1.0, 0.0, 0.0])])
    store.upsert_file("decisions/d.md", 1.0, "h", [("D", "alpha", [1.0, 0.0, 0.0])])
    hits = store.knn([1.0, 0.0, 0.0], k=5, exclude_prefixes=("decisions/",))
    assert {h.path for h in hits} == {"canon/doc.md"}


def test_empty_file_is_tracked_without_vectors(tmp_path):
    store = VectorStore(tmp_path / "i.db")
    store.upsert_file("empty.md", 1.0, "h", chunks=[])
    assert store.file_state("empty.md") == (1.0, "h")
    assert "empty.md" in store.indexed_paths()
    assert store.knn([1.0, 0.0, 0.0], k=5) == []
