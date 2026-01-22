from __future__ import annotations

import sqlite3
from typing import Iterable

import numpy as np

from openrecall.shared.config import settings


def _fit_dim(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32, copy=False)
    if vec.ndim != 1:
        vec = vec.reshape(-1).astype(np.float32, copy=False)
    dim = int(settings.embedding_dim)
    if vec.shape[0] == dim:
        return vec
    if vec.shape[0] > dim:
        return vec[:dim]
    out = np.zeros(dim, dtype=np.float32)
    out[: vec.shape[0]] = vec
    return out


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec.astype(np.float32, copy=False)
    return (vec / norm).astype(np.float32, copy=False)


class CacheVectorBackend:
    def __init__(self) -> None:
        self._vectors: dict[int, np.ndarray] = {}

    def upsert(self, entry_id: int, vec: np.ndarray) -> None:
        if vec is None:
            return
        v = _fit_dim(vec)
        v = _l2_normalize(v)
        self._vectors[int(entry_id)] = v

    def bulk_upsert(self, items: Iterable[tuple[int, np.ndarray]]) -> None:
        for entry_id, vec in items:
            self.upsert(entry_id, vec)

    def query(
        self,
        query_vec: np.ndarray,
        topk: int = 50,
        candidate_ids: Iterable[int] | None = None,
    ) -> list[tuple[int, float]]:
        q = _l2_normalize(_fit_dim(query_vec))
        ids = list(candidate_ids) if candidate_ids is not None else list(self._vectors.keys())
        if not ids:
            return []
        mat = np.stack([self._vectors[i] for i in ids], axis=0)
        scores = mat @ q
        k = min(int(topk), scores.shape[0])
        if k <= 0:
            return []
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_sorted = top_idx[np.argsort(-scores[top_idx])]
        return [(int(ids[i]), float(scores[i])) for i in top_sorted]


class SQLiteVSSBackend:
    def __init__(self, conn: sqlite3.Connection) -> None:
        import sqlite_vss  # type: ignore

        self._conn = conn
        self._conn.enable_load_extension(True)
        sqlite_vss.load(self._conn)
        self._conn.enable_load_extension(False)

        dim = int(settings.embedding_dim)
        cur = self._conn.cursor()
        cur.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vss_entries USING vss0(image_embedding({dim}))"
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def upsert(self, entry_id: int, vec: np.ndarray) -> None:
        v = _l2_normalize(_fit_dim(vec))
        cur = self._conn.cursor()
        cur.execute("DELETE FROM vss_entries WHERE rowid = ?", (int(entry_id),))
        cur.execute(
            "INSERT INTO vss_entries(rowid, image_embedding) VALUES (?, ?)",
            (int(entry_id), v.astype(np.float32).tobytes()),
        )
        self._conn.commit()

    def bulk_upsert(self, items: Iterable[tuple[int, np.ndarray]]) -> None:
        cur = self._conn.cursor()
        for entry_id, vec in items:
            v = _l2_normalize(_fit_dim(vec))
            cur.execute("DELETE FROM vss_entries WHERE rowid = ?", (int(entry_id),))
            cur.execute(
                "INSERT INTO vss_entries(rowid, image_embedding) VALUES (?, ?)",
                (int(entry_id), v.astype(np.float32).tobytes()),
            )
        self._conn.commit()

    def query(
        self,
        query_vec: np.ndarray,
        topk: int = 50,
        candidate_ids: Iterable[int] | None = None,
    ) -> list[tuple[int, float]]:
        q = _l2_normalize(_fit_dim(query_vec)).astype(np.float32).tobytes()
        limit = int(topk)
        if limit <= 0:
            return []
        cur = self._conn.cursor()
        if candidate_ids is None:
            cur.execute(
                "SELECT rowid, distance FROM vss_entries "
                "WHERE vss_search(image_embedding, ?) "
                "LIMIT ?",
                (q, limit),
            )
            rows = cur.fetchall()
        else:
            ids = [int(i) for i in candidate_ids]
            if not ids:
                return []
            placeholders = ",".join(["?"] * len(ids))
            cur.execute(
                "SELECT rowid, distance FROM vss_entries "
                "WHERE vss_search(image_embedding, ?) AND rowid IN (" + placeholders + ") "
                "LIMIT ?",
                (q, *ids, limit),
            )
            rows = cur.fetchall()
        return [(int(r[0]), float(-float(r[1]))) for r in rows]


def get_vector_backend() -> CacheVectorBackend | SQLiteVSSBackend:
    backend = (settings.vector_backend or "cache").strip().lower()
    if backend == "sqlite_vss":
        try:
            import sqlite_vss  # type: ignore

            _ = sqlite_vss
        except Exception:
            return CacheVectorBackend()
        conn = sqlite3.connect(str(settings.db_path))
        try:
            return SQLiteVSSBackend(conn)
        except Exception:
            conn.close()
            return CacheVectorBackend()
    return CacheVectorBackend()
