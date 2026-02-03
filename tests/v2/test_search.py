
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from openrecall.server.search.engine import SearchEngine
from openrecall.server.schema import SemanticSnapshot, Context, Content

@pytest.fixture
def mock_search_engine(mock_settings, mock_ai_provider):
    """Create a SearchEngine with mocked stores."""
    with patch("openrecall.server.search.engine.VectorStore") as MockVectorStore, \
         patch("openrecall.server.search.engine.SQLStore") as MockSQLStore, \
         patch("openrecall.server.search.engine.get_ai_provider", return_value=mock_ai_provider), \
         patch("openrecall.server.search.engine.get_reranker") as MockGetReranker:
        
        # Mock the reranker to return zeros by default (simulating failure or no-op)
        # This prevents it from altering scores in tests that check Stage 1/2 logic
        mock_reranker = MagicMock()
        mock_reranker.compute_score.return_value = [0.0] * 50 # Return 0s so engine keeps RRF order
        MockGetReranker.return_value = mock_reranker

        engine = SearchEngine()
        yield engine, MockVectorStore.return_value, MockSQLStore.return_value

def create_snapshot(id, score=0.0):
    return SemanticSnapshot(
        id=id,
        image_path="/tmp/test.png",
        embedding_vector=[0.0]*1024,
        context=Context(
            app_name="App", window_title="Title", timestamp=1000.0, time_bucket="bucket"
        ),
        content=Content(
            ocr_text="text", caption="caption", keywords=[], scene_tag="", action_tag="", ocr_head="text"
        )
    )

def test_search_vector_only(mock_search_engine):
    """Test pure vector search results."""
    engine, vector_store, sql_store = mock_search_engine
    
    # Setup Vector Results: [(Snapshot, Score, Distance, Metric)]
    snap1 = create_snapshot("id1")
    vector_store.search.return_value = [
        (snap1, 0.8, 0.2, "cosine")
    ]
    # Setup SQL Results: Empty
    sql_store.search.return_value = []
    
    results = engine.search("query")
    
    assert len(results) == 1
    assert results[0].id == "id1"
    assert results[0].score == 0.8

def test_search_hybrid_boosting(mock_search_engine):
    """Test that FTS matches boost vector scores."""
    engine, vector_store, sql_store = mock_search_engine
    
    snap1 = create_snapshot("id1")
    
    # Vector gives 0.5 score
    vector_store.search.return_value = [(snap1, 0.5, 0.5, "cosine")]
    
    # FTS matches "id1" at Rank 0 (Top match)
    # sql_store.search returns list of (id, bm25_score)
    sql_store.search.return_value = [("id1", 10.0)]
    
    results = engine.search("query")
    
    assert len(results) == 1
    # Boost formula: score + 0.3 * (1.0 - rank/count)
    # Rank=0, Count=1 => Boost = 0.3 * (1.0 - 0) = 0.3
    # Expected: 0.5 + 0.3 = 0.8
    assert results[0].score == 0.8

def test_search_fts_rescue(mock_search_engine):
    """Test that items only in FTS are rescued."""
    engine, vector_store, sql_store = mock_search_engine
    
    # Vector finds nothing
    vector_store.search.return_value = []
    
    # FTS finds "id2"
    sql_store.search.return_value = [("id2", 5.0)]
    
    # We need vector_store.get_snapshots to return the object for id2
    snap2 = create_snapshot("id2")
    vector_store.get_snapshots.return_value = [snap2]
    
    results = engine.search("query")
    
    assert len(results) == 1
    assert results[0].id == "id2"
    # Rescued items get base score 0.2 + boost
    # Boost: 0.3 * (1.0 - 0/1) = 0.3
    # Total: 0.2 + 0.3 = 0.5
    assert results[0].score == 0.5

def test_search_time_filter(mock_search_engine):
    """Test that time filters are passed to vector store."""
    engine, vector_store, sql_store = mock_search_engine
    
    vector_store.search.return_value = []
    sql_store.search.return_value = []
    
    engine.search("query today")
    
    # Check that 'where' clause was constructed
    # Note: SearchEngine might call vector_store.search twice (once for filtered, once for debug unfiltered)
    # We want the first call which has the filter
    call_args_list = vector_store.search.call_args_list
    assert len(call_args_list) >= 1
    
    # Check the first call
    _, kwargs = call_args_list[0]
    where_clause = kwargs.get("where")
    
    assert where_clause is not None
    assert "timestamp >=" in where_clause
