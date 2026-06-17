"""sqlite-vec vector store: a single-file index of embedded doc chunks + KNN search.

Vectors are L2-normalized on the way in and on query, so sqlite-vec's default L2 KNN
ranks identically to cosine similarity -- portable across platforms and sqlite-vec versions
without depending on a specific distance metric. The store also tracks per-file (mtime, hash)
so ingest can be incremental.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec


@dataclass(frozen=True)
class Hit:
    path: str
    heading: str
    text: str
    distance: float
    ord: int


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else list(vec)


class VectorStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self._init_schema()
        self._dim = self._read_dim()

    # --- schema / meta ---------------------------------------------------
    def _init_schema(self) -> None:
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, hash TEXT)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS chunks("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, heading TEXT, text TEXT, ord INTEGER)"
            )
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")

    def _read_dim(self) -> int | None:
        row = self.db.execute("SELECT value FROM meta WHERE key='dim'").fetchone()
        return int(row[0]) if row else None

    def _ensure_vec(self, dim: int) -> None:
        if self._dim is None:
            self.db.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{dim}])"
            )
            self.db.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('dim', ?)", (str(dim),)
            )
            self._dim = dim
        elif dim != self._dim:
            raise ValueError(
                f"embedding dim {dim} != index dim {self._dim} "
                f"(embedding model changed? rebuild the index at {self.path})"
            )

    # --- writes ----------------------------------------------------------
    def upsert_file(
        self,
        path: str,
        mtime: float,
        content_hash: str,
        chunks: list[tuple[str, str, list[float]]],
    ) -> None:
        """Replace all chunks for `path` and record its (mtime, hash). `chunks` may be empty."""
        with self.db:
            self._delete_chunks(path)
            for ord_, (heading, text, embedding) in enumerate(chunks):
                self._ensure_vec(len(embedding))
                cur = self.db.execute(
                    "INSERT INTO chunks(path, heading, text, ord) VALUES(?, ?, ?, ?)",
                    (path, heading, text, ord_),
                )
                self.db.execute(
                    "INSERT INTO vec_chunks(rowid, embedding) VALUES(?, ?)",
                    (cur.lastrowid, sqlite_vec.serialize_float32(_normalize(embedding))),
                )
            self.db.execute(
                "INSERT OR REPLACE INTO files(path, mtime, hash) VALUES(?, ?, ?)",
                (path, mtime, content_hash),
            )

    def _delete_chunks(self, path: str) -> None:
        ids = [r[0] for r in self.db.execute("SELECT id FROM chunks WHERE path=?", (path,))]
        if ids and self._dim is not None:
            self.db.executemany("DELETE FROM vec_chunks WHERE rowid=?", [(i,) for i in ids])
        self.db.execute("DELETE FROM chunks WHERE path=?", (path,))

    def delete_file(self, path: str) -> None:
        with self.db:
            self._delete_chunks(path)
            self.db.execute("DELETE FROM files WHERE path=?", (path,))

    def touch(self, path: str, mtime: float) -> None:
        with self.db:
            self.db.execute("UPDATE files SET mtime=? WHERE path=?", (mtime, path))

    # --- reads -----------------------------------------------------------
    def file_state(self, path: str) -> tuple[float, str] | None:
        row = self.db.execute("SELECT mtime, hash FROM files WHERE path=?", (path,)).fetchone()
        return (row[0], row[1]) if row else None

    def indexed_paths(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT path FROM files")]

    def knn(
        self,
        embedding: list[float],
        *,
        k: int = 5,
        exclude_prefixes: tuple[str, ...] = (),
    ) -> list[Hit]:
        if self._dim is None:
            return []
        fetch = k * 5 + 10 if exclude_prefixes else k
        rows = self.db.execute(
            "SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? "
            "ORDER BY distance LIMIT ?",
            (sqlite_vec.serialize_float32(_normalize(embedding)), fetch),
        ).fetchall()
        hits: list[Hit] = []
        for rowid, distance in rows:
            row = self.db.execute(
                "SELECT path, heading, text, ord FROM chunks WHERE id=?", (rowid,)
            ).fetchone()
            if row is None:
                continue
            path, heading, text, ord_ = row
            if any(path.startswith(p) for p in exclude_prefixes):
                continue
            hits.append(Hit(path=path, heading=heading, text=text, distance=distance, ord=ord_))
            if len(hits) >= k:
                break
        return hits

    def close(self) -> None:
        self.db.close()
