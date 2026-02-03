
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from openrecall.server.search.engine import SearchEngine, construct_rerank_context
from openrecall.server.schema import SemanticSnapshot, Context, Content

# --- Fixtures ---

@pytest.fixture
def sample_snapshot():
    return SemanticSnapshot(
        id="test-uuid-123",
        image_path="/tmp/img.png",
        context=Context(
            app_name="VS Code",
            window_title="engine.py - MyRecall",
            timestamp=1706248800.0, # 2024-01-26 14:00:00 UTC (approx)
            time_bucket="2024-01-26-14"
        ),
        content=Content(
            ocr_text="def search(self): pass",
            ocr_head="def search(self): pass",
            caption="Coding in Python",
            scene_tag="coding",
            keywords=["python", "search"]
        ),
        embedding_vector=[0.0]*1024
    )

@pytest.fixture
def mock_stores():
    vector_store = MagicMock()
    sql_store = MagicMock()
    return vector_store, sql_store

# --- Tests ---

def test_construct_rerank_context(sample_snapshot):
    context_str = construct_rerank_context(sample_snapshot)
    
    # Check for presence of key sections
    assert "[Metadata]" in context_str
    assert "App: VS Code" in context_str
    assert "Title: engine.py - MyRecall" in context_str
    
    assert "[Visual Context]" in context_str
    assert "Scene: coding" in context_str
    assert "Summary: Coding in Python" in context_str
    
    assert "[OCR Content]" in context_str
    assert "def search(self): pass" in context_str
    
    # Check timestamp formatting (day of week)
    # 1706248800 is Jan 26 2024, which is a Friday
    assert "2024-01-26" in context_str

class TestSearchEngineRerank:
    
    @pytest.fixture
    def engine(self, mock_stores, mock_ai_provider, mock_settings):
        vector_store, sql_store = mock_stores
        
        # Patch get_ai_provider to avoid real model loading
        with patch('openrecall.server.search.engine.get_ai_provider', return_value=mock_ai_provider), \
             patch('openrecall.server.search.engine.settings', mock_settings):
             
            # Initialize engine
            # We also need to patch get_reranker inside __init__
            with patch('openrecall.server.search.engine.get_reranker') as mock_get_reranker:
                self.mock_reranker = MagicMock()
                mock_get_reranker.return_value = self.mock_reranker
                
                engine = SearchEngine(vector_store, sql_store)
                return engine

    def test_search_reranking_flow(self, engine, sample_snapshot):
        # Setup mock results from Vector/FTS
        # We need 2 candidates to test re-ordering
        
        snap1 = sample_snapshot.model_copy()
        snap1.id = "id-1"
        snap1.context.app_name = "App 1"
        
        snap2 = sample_snapshot.model_copy()
        snap2.id = "id-2"
        snap2.context.app_name = "App 2"
        
        # Mock Vector Store returns (snapshot, score, distance, metric)
        engine.vector_store.search.return_value = [
            (snap1, 0.8, 0.2, "cosine"),
            (snap2, 0.7, 0.3, "cosine")
        ]
        
        # Mock FTS returns empty for simplicity (so pure vector results)
        engine.sql_store.search.return_value = []
        
        # Mock Reranker to flip the order: give snap2 a higher score than snap1
        # Input order to reranker will be [snap1, snap2] (based on vector score)
        # We return [0.1, 0.9] -> snap2 should become #1
        engine.reranker.compute_score.return_value = [0.1, 0.9]
        
        # Execute Search
        results = engine.search("test query")
        
        # Verify Reranker was called
        engine.reranker.compute_score.assert_called_once()
        call_args = engine.reranker.compute_score.call_args
        assert call_args[0][0] == "test query" # Query
        assert len(call_args[0][1]) == 2 # 2 Docs
        
        # Verify Results are Re-ordered
        assert len(results) == 2
        assert results[0].id == "id-2"
        assert results[0].score == 0.9
        
        assert results[1].id == "id-1"
        assert results[1].score == 0.1

    def test_search_reranking_fallback(self, engine, sample_snapshot):
        # Test case where reranker fails (returns all zeros)
        # Original order should be preserved
        
        snap1 = sample_snapshot.model_copy()
        snap1.id = "id-1" # Score 0.8
        
        snap2 = sample_snapshot.model_copy()
        snap2.id = "id-2" # Score 0.7
        
        engine.vector_store.search.return_value = [
            (snap1, 0.8, 0.2, "cosine"),
            (snap2, 0.7, 0.3, "cosine")
        ]
        engine.sql_store.search.return_value = []
        
        # Reranker returns zeros (failure/timeout)
        engine.reranker.compute_score.return_value = [0.0, 0.0]
        
        results = engine.search("test query")
        
        # Order should match vector score (snap1 first)
        assert results[0].id == "id-1"
        assert results[1].id == "id-2"
        
        # Scores should be original vector scores (0.8, 0.7)
        # Note: In the implementation, if reranker returns 0s, we keep RRF scores
        # Here RRF score is approx same as vector score since FTS is empty
        assert results[0].score == 0.8
        assert results[1].score == 0.7

    def test_search_debug_output(self, engine, sample_snapshot):
        # Verify debug output contains rerank info
        snap1 = sample_snapshot.model_copy()
        snap1.id = "id-1"
        
        engine.vector_store.search.return_value = [(snap1, 0.8, 0.2, "cosine")]
        engine.sql_store.search.return_value = []
        engine.reranker.compute_score.return_value = [0.95]
        
        results = engine.search_debug("test query")
        
        assert len(results) == 1
        item = results[0]
        assert item["rerank_score"] == 0.95
        assert item["rerank_rank"] == 0
        assert item["final_score"] == 0.95
        assert item["combined_rank"] == 0 # Should be 0 before reranking

    def test_combined_rank_logic(self, engine, sample_snapshot):
        # Test combined rank assignment before reranking
        snap1 = sample_snapshot.model_copy()
        snap1.id = "id-1"
        snap2 = sample_snapshot.model_copy()
        snap2.id = "id-2"
        
        # Vector search returns snap1 > snap2
        engine.vector_store.search.return_value = [
            (snap1, 0.8, 0.2, "cosine"),
            (snap2, 0.7, 0.3, "cosine")
        ]
        engine.sql_store.search.return_value = []
        
        # Reranker flips order: snap2 > snap1
        engine.reranker.compute_score.return_value = [0.1, 0.9]
        
        results = engine.search_debug("test query")
        
        # Check Final Order (Reranked)
        assert results[0]['id'] == "id-2"
        assert results[1]['id'] == "id-1"
        
        # Check Combined Ranks (Original Order)
        # snap2 was originally #2 (index 1)
        assert results[0]['combined_rank'] == 1 
        # snap1 was originally #1 (index 0)
        assert results[1]['combined_rank'] == 0

