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
        if not q or q.isspace():
            return [], 0

        # Get query embedding
        from openrecall.server.ai.factory import get_multimodal_embedding_provider
        provider = get_multimodal_embedding_provider()
        query_vector = provider.embed_text(q)

        # Search embeddings with distance scores
        embeddings_with_distance = self._embedding_store.search_with_distance(
            query_vector.tolist(), limit=limit + offset
        )

        results = []
        for emb, distance in embeddings_with_distance[offset : offset + limit]:
            # Convert cosine distance to cosine similarity (cosine_sim = 1 - cosine_dist)
            cosine_score = 1.0 - float(distance)
            results.append({
                "frame_id": emb.frame_id,
                "cosine_score": cosine_score,
                "timestamp": emb.timestamp,
                "text": "",  # Will need to fetch from frames if needed
                "app_name": emb.app_name,
                "window_name": emb.window_name,
                "browser_url": None,
                "focused": None,
                "device_name": "monitor_0",
                "file_path": f"{emb.timestamp}.jpg",
                "frame_url": f"/v1/frames/{emb.frame_id}",
                "tags": [],
            })

        return results, len(embeddings_with_distance)

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
            # Store cosine scores for later use
            for e, d in embeddings_with_distance:
                vector_similarities[e.frame_id] = 1.0 - float(d)

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
        for frame_id in frame_ids:
            frame = frame_data_map.get(frame_id, {})
            results.append({
                "frame_id": frame_id,
                "hybrid_score": scores.get(frame_id, 0.0),
                "cosine_score": vector_similarities.get(frame_id),  # Raw vector similarity
                "timestamp": frame.get("timestamp", ""),
                "text": frame.get("full_text", "")[:200] if frame.get("full_text") else "",
                "app_name": frame.get("app_name", ""),
                "window_name": frame.get("window_name", ""),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "file_path": frame.get("file_path", f"{frame.get('timestamp', '')}.jpg"),
                "frame_url": f"/v1/frames/{frame_id}",
                "tags": [],
            })

        return results, total
