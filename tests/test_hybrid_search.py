"""Tests for hybrid search (FTS + vector)."""
import pytest

from openrecall.server.search.hybrid_engine import (
    reciprocal_rank_fusion,
    HybridSearchEngine,
)


class TestReciprocalRankFusion:
    def test_rrf_merges_results(self):
        """RRF should merge FTS and vector results."""
        fts_results = [
            {"frame_id": 1, "text": "result 1"},
            {"frame_id": 2, "text": "result 2"},
            {"frame_id": 3, "text": "result 3"},
        ]
        vector_results = [
            {"frame_id": 3, "similarity": 0.95},
            {"frame_id": 1, "similarity": 0.90},
            {"frame_id": 4, "similarity": 0.85},
        ]

        merged = reciprocal_rank_fusion(
            fts_results=fts_results,
            vector_results=vector_results,
        )

        # Frame 1 and 3 appear in both - should rank higher
        frame_ids = [m[0] for m in merged]
        assert 1 in frame_ids
        assert 3 in frame_ids
        # Frame 1 and 3 should be in top positions
        assert frame_ids[0] in [1, 3]

    def test_rrf_empty_inputs(self):
        """RRF should handle empty inputs."""
        result = reciprocal_rank_fusion([], [])
        assert result == []

        result = reciprocal_rank_fusion([{"frame_id": 1}], [])
        assert result == [(1, pytest.approx(0.5 / 61, rel=0.01))]

    def test_rrf_weights(self):
        """RRF should respect weight parameters."""
        fts_results = [{"frame_id": 1}]
        vector_results = [{"frame_id": 2}]

        # Higher FTS weight should favor FTS result
        merged_fts = reciprocal_rank_fusion(
            fts_results, vector_results, fts_weight=0.9, vector_weight=0.1
        )
        merged_vec = reciprocal_rank_fusion(
            fts_results, vector_results, fts_weight=0.1, vector_weight=0.9
        )

        # Frame 1 score should be higher in fts_weighted
        fts_score_1 = next(s for f, s in merged_fts if f == 1)
        vec_score_1 = next(s for f, s in merged_vec if f == 1)
        assert fts_score_1 > vec_score_1
