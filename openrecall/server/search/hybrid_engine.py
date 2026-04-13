# openrecall/server/search/hybrid_engine.py
"""Hybrid search engine combining FTS5 and vector search."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    fts_results: List[Dict[str, Any]],
    vector_results: List[Dict[str, Any]],
    k: int = 60,
    fts_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> List[Tuple[int, float]]:
    """Merge FTS and vector search results using RRF.

    RRF formula: score = weight / (k + rank)

    Args:
        fts_results: FTS search results with 'frame_id' key
        vector_results: Vector search results with 'frame_id' key
        k: RRF smoothing parameter (default 60)
        fts_weight: Weight for FTS results (default 0.5)
        vector_weight: Weight for vector results (default 0.5)

    Returns:
        List of (frame_id, score) tuples sorted by score descending
    """
    scores = defaultdict(float)

    # Process FTS results
    for rank, result in enumerate(fts_results, start=1):
        frame_id = result.get("frame_id")
        if frame_id is not None:
            scores[frame_id] += fts_weight / (k + rank)

    # Process vector results
    for rank, result in enumerate(vector_results, start=1):
        frame_id = result.get("frame_id")
        if frame_id is not None:
            scores[frame_id] += vector_weight / (k + rank)

    # Sort by score descending
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridSearchEngine:
    """Hybrid search combining FTS5 and vector similarity."""

    def __init__(self):
        from openrecall.server.search.engine import SearchEngine
        from openrecall.server.database.embedding_store import EmbeddingStore

        self._fts_engine = SearchEngine()
        self._embedding_store = EmbeddingStore()

    def search(
        self,
        q: str = "",
        mode: str = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Execute hybrid search.

        Args:
            q: Text query
            mode: 'fts', 'vector', or 'hybrid' (default)
            fts_weight: Weight for FTS results in hybrid mode
            vector_weight: Weight for vector results in hybrid mode
            limit: Max results
            offset: Pagination offset
            **kwargs: Additional filters passed to FTS engine

        Returns:
            Tuple of (results list, total count)
        """
        mode = mode.lower().strip()
        if mode not in ("fts", "vector", "hybrid"):
            mode = "hybrid"

        if mode == "fts":
            return self._fts_only_search(q, limit, offset, **kwargs)
        elif mode == "vector":
            return self._vector_only_search(q, limit, offset)
        else:
            return self._hybrid_search(
                q, fts_weight, vector_weight, limit, offset, **kwargs
            )

    def _fts_only_search(
        self, q: str, limit: int, offset: int, **kwargs
    ) -> Tuple[List[Dict[str, Any]], int]:
        """FTS-only search."""
        return self._fts_engine.search(q=q, limit=limit, offset=offset, **kwargs)

    def _vector_only_search(
        self, q: str, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Vector-only search."""
        from openrecall.server.database.frames_store import FramesStore

        frames_store = FramesStore()

        # If no query, return recent frames with embeddings (browse mode)
        if not q or q.isspace():
            return self._get_recent_embedded_frames(frames_store, limit, offset)

        # Get query embedding
        from openrecall.server.ai.factory import get_multimodal_embedding_provider
        provider = get_multimodal_embedding_provider()
        query_vector = provider.embed_text(q)

        # Search embeddings with distance scores
        embeddings_with_distance = self._embedding_store.search_with_distance(
            query_vector.tolist(), limit=limit + offset
        )

        # Collect frame IDs to fetch full frame data
        frame_ids = []
        vector_similarities = {}
        for emb, distance in embeddings_with_distance:
            frame_ids.append(emb.frame_id)
            vector_similarities[emb.frame_id] = 1.0 - float(distance)

        # Fetch full frame data from database
        frame_data_map = frames_store.get_frames_by_ids(frame_ids)

        results = []
        for emb, distance in embeddings_with_distance[offset : offset + limit]:
            frame_id = emb.frame_id
            frame = frame_data_map.get(frame_id, {})
            # Convert cosine distance to cosine similarity (cosine_sim = 1 - cosine_dist)
            cosine_score = 1.0 - float(distance)
            results.append({
                "frame_id": frame_id,
                "cosine_score": cosine_score,
                "timestamp": frame.get("timestamp", emb.timestamp),
                "text": frame.get("full_text", "")[:200] if frame.get("full_text") else "",
                "text_source": frame.get("text_source", "ocr"),
                "app_name": frame.get("app_name", emb.app_name),
                "window_name": frame.get("window_name", emb.window_name),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "file_path": frame.get("file_path", f"{emb.timestamp}.jpg"),
                "frame_url": f"/v1/frames/{frame_id}",
                "tags": [],
                "embedding_status": frame.get("embedding_status", ""),
            })

        return results, len(embeddings_with_distance)

    def _get_recent_embedded_frames(
        self, frames_store, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get recent frames that have embeddings (browse mode for vector search)."""
        import sqlite3

        try:
            conn = sqlite3.connect(str(frames_store.db_path))
            conn.row_factory = sqlite3.Row

            # Count total frames with embeddings
            count_row = conn.execute(
                """
                SELECT COUNT(*) as total FROM frames
                WHERE embedding_status = 'completed' AND status = 'completed'
                """
            ).fetchone()
            total = count_row["total"] if count_row else 0

            # Get recent frames with embeddings
            rows = conn.execute(
                """
                SELECT id as frame_id, timestamp, full_text, text_source,
                       app_name, window_name, browser_url, focused,
                       device_name, file_path, embedding_status
                FROM frames
                WHERE embedding_status = 'completed' AND status = 'completed'
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

            results = []
            for row in rows:
                ts = row["timestamp"]
                results.append({
                    "frame_id": row["frame_id"],
                    "cosine_score": None,
                    "timestamp": ts,
                    "text": row["full_text"] or "",
                    "text_source": row["text_source"] or "ocr",
                    "app_name": row["app_name"],
                    "window_name": row["window_name"],
                    "browser_url": row["browser_url"],
                    "focused": bool(row["focused"]) if row["focused"] is not None else None,
                    "device_name": row["device_name"] or "monitor_0",
                    "file_path": row["file_path"] or f"{ts}.jpg",
                    "frame_url": f"/v1/frames/{row['frame_id']}",
                    "tags": [],
                    "embedding_status": row["embedding_status"] or "",
                })

            conn.close()
            return results, total

        except sqlite3.Error as e:
            logger.error("Failed to get recent embedded frames: %s", e)
            return [], 0

    def _hybrid_search(
        self,
        q: str,
        fts_weight: float,
        vector_weight: float,
        limit: int,
        offset: int,
        **kwargs,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Hybrid search with RRF fusion."""
        # Run both searches in parallel (for now, sequentially)
        fts_results, _ = self._fts_engine.search(q=q, limit=limit * 2, **kwargs)

        vector_results = []
        vector_similarities = {}  # frame_id -> cosine_score
        vector_ranks = {}  # frame_id -> rank in vector results
        if q and not q.isspace():
            from openrecall.server.ai.factory import get_multimodal_embedding_provider
            provider = get_multimodal_embedding_provider()
            query_vector = provider.embed_text(q)
            embeddings_with_distance = self._embedding_store.search_with_distance(
                query_vector.tolist(), limit=limit * 2
            )
            vector_results = [
                {"frame_id": e.frame_id, "similarity": 1.0 - float(d)}  # cosine_sim = 1 - dist
                for e, d in embeddings_with_distance
            ]
            # Store cosine scores and ranks for later use
            for rank, (e, d) in enumerate(embeddings_with_distance, start=1):
                vector_similarities[e.frame_id] = 1.0 - float(d)
                vector_ranks[e.frame_id] = rank

        # Build FTS rank and BM25 score maps from FTS results
        fts_ranks = {r["frame_id"]: idx + 1 for idx, r in enumerate(fts_results)}
        fts_bm25_scores = {r["frame_id"]: r.get("fts_rank") for r in fts_results}

        # Merge with RRF
        merged = reciprocal_rank_fusion(
            fts_results, vector_results, fts_weight=fts_weight, vector_weight=vector_weight
        )

        # Apply pagination
        total = len(merged)
        merged = merged[offset : offset + limit]

        # Build final results - fetch full frame data from database
        frame_ids = [frame_id for frame_id, _ in merged]
        scores = {frame_id: score for frame_id, score in merged}

        # Fetch full frame data from frames table
        from openrecall.server.database.frames_store import FramesStore
        frames_store = FramesStore()
        frame_data_map = frames_store.get_frames_by_ids(frame_ids)

        results = []
        for hybrid_rank, frame_id in enumerate(frame_ids, start=offset + 1):
            frame = frame_data_map.get(frame_id, {})
            results.append({
                "frame_id": frame_id,
                "hybrid_score": scores.get(frame_id, 0.0),
                "hybrid_rank": hybrid_rank,
                "cosine_score": vector_similarities.get(frame_id),  # Raw vector similarity
                "vector_rank": vector_ranks.get(frame_id),  # Rank in vector search results
                "fts_rank": fts_bm25_scores.get(frame_id),  # BM25 score from FTS results
                "fts_result_rank": fts_ranks.get(frame_id),  # Rank in FTS search results
                "timestamp": frame.get("timestamp", ""),
                "text": frame.get("full_text", "")[:200] if frame.get("full_text") else "",
                "text_source": frame.get("text_source", "ocr"),
                "app_name": frame.get("app_name", ""),
                "window_name": frame.get("window_name", ""),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "file_path": frame.get("file_path", f"{frame.get('timestamp', '')}.jpg"),
                "frame_url": f"/v1/frames/{frame_id}",
                "tags": [],
                "embedding_status": frame.get("embedding_status", ""),
            })

        return results, total
