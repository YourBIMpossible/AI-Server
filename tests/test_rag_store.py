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


def test_knn_finds_a_match_beyond_the_initial_overfetch_when_excluding(tmp_path):
    # RAG-6: the old fixed over-fetch (k*5+10) could return [] if every one of the
    # top `fetch` rows happened to be excluded, even though a real match existed
    # further down the ranking. The fetch must grow until k survive or the index
    # is exhausted, not give up after the first fixed-size page.
    store = VectorStore(tmp_path / "i.db")
    for i in range(20):  # 20 near-identical "decisions/" vectors outrank the real match
        store.upsert_file(f"decisions/d{i}.md", 1.0, "h", [("D", "x", [1.0, 0.0001 * i, 0.0])])
    store.upsert_file("canon/doc.md", 1.0, "h", [("C", "x", [0.99, 0.2, 0.0])])

    hits = store.knn([1.0, 0.0, 0.0], k=1, exclude_prefixes=("decisions/",))
    assert len(hits) == 1
    assert hits[0].path == "canon/doc.md"


def test_upsert_rejects_non_finite_embedding(tmp_path):
    # RAG-2 (store): a NaN/inf embedding must never reach the index -- it would
    # propagate into `distance`, making ORDER BY distance undefined and defeating
    # the max_distance grounding guard (a NaN comparison is always False).
    store = VectorStore(tmp_path / "i.db")
    try:
        store.upsert_file("a.md", 1.0, "h", [("S", "x", [1.0, float("nan"), 0.0])])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "non-finite" in str(e)


def test_upsert_rejects_zero_norm_embedding(tmp_path):
    # A zero vector can't be normalized to unit length, breaking the L2==cosine
    # invariant every stored distance relies on.
    store = VectorStore(tmp_path / "i.db")
    try:
        store.upsert_file("a.md", 1.0, "h", [("S", "x", [0.0, 0.0, 0.0])])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "zero" in str(e).lower()


def test_upsert_rejects_empty_embedding(tmp_path):
    store = VectorStore(tmp_path / "i.db")
    try:
        store.upsert_file("a.md", 1.0, "h", [("S", "x", [])])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "empty" in str(e).lower()


def test_upsert_rejecting_one_chunk_leaves_prior_index_state_intact(tmp_path):
    # The bad-embedding raise happens inside the same `with self.db:` transaction
    # as the delete-old-chunks step, so a failure partway through a multi-chunk
    # file must roll back cleanly rather than leaving the file half-updated.
    store = VectorStore(tmp_path / "i.db")
    store.upsert_file("a.md", 1.0, "h1", _chunks())
    assert store.file_state("a.md") == (1.0, "h1")

    try:
        store.upsert_file(
            "a.md",
            2.0,
            "h2",
            [("Good", "x", [1.0, 0.0, 0.0]), ("Bad", "y", [0.0, 0.0, 0.0])],
        )
        assert False, "expected ValueError"
    except ValueError:
        pass

    # prior state (mtime/hash AND chunks) must be unchanged, not half-updated
    assert store.file_state("a.md") == (1.0, "h1")
    hits = store.knn([1.0, 0.0, 0.0], k=5)
    assert {h.text for h in hits} == {"alpha", "beta"}


def test_store_uses_wal_journal_mode_with_a_busy_timeout(tmp_path):
    # RAG-5 (store): the default rollback-journal mode + busy_timeout=0 means a
    # reader opening while a scheduled ingest holds its write transaction fails
    # immediately with "database is locked" instead of waiting briefly.
    store = VectorStore(tmp_path / "i.db")
    mode = store.db.execute("PRAGMA journal_mode").fetchone()[0]
    timeout = store.db.execute("PRAGMA busy_timeout").fetchone()[0]
    assert mode.lower() == "wal"
    assert timeout >= 5000


def test_empty_file_is_tracked_without_vectors(tmp_path):
    store = VectorStore(tmp_path / "i.db")
    store.upsert_file("empty.md", 1.0, "h", chunks=[])
    assert store.file_state("empty.md") == (1.0, "h")
    assert "empty.md" in store.indexed_paths()
    assert store.knn([1.0, 0.0, 0.0], k=5) == []
