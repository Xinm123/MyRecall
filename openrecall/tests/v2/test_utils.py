
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from openrecall.server.utils.keywords import KeywordExtractor
from openrecall.server.utils.fusion import build_fusion_text
from openrecall.server.utils.query_parser import QueryParser
from openrecall.server.schema import SemanticSnapshot, Context, Content

def test_keyword_extractor_stopwords():
    """Test that stopwords are removed."""
    extractor = KeywordExtractor()
    text = "The quick brown fox jumps over the lazy dog and it was good"
    keywords = extractor.extract(text)
    
    # Common stopwords like 'the', 'and', 'it', 'was' should be gone
    assert "the" not in keywords
    assert "and" not in keywords
    # 'fox', 'brown', 'quick' should remain (if length >= 3)
    assert "fox" in keywords or "quick" in keywords

def test_keyword_extractor_code_filter():
    """Test that programming keywords are handled correctly (currently filtered out)."""
    extractor = KeywordExtractor()
    text = "def function class import return"
    keywords = extractor.extract(text)
    
    # According to STOPWORDS list in keywords.py, 'def', 'class', 'import' are stopwords
    assert "def" not in keywords
    assert "class" not in keywords

def test_fusion_text_builder():
    """Test that fusion text is constructed with correct tags."""
    snapshot = SemanticSnapshot(
        id="test-id",
        image_path="/tmp/test.png",
        embedding_vector=[0.0]*1024,
        context=Context(
            app_name="VS Code",
            window_title="test.py",
            timestamp=1234567890.0,
            time_bucket="2023-01-01-12"
        ),
        content=Content(
            ocr_text="import os\nprint('hello')",
            ocr_head="import os",
            caption="A code screenshot",
            keywords=["python", "code"],
            scene_tag="coding",
            action_tag="typing"
        )
    )
    
    fusion = build_fusion_text(snapshot)
    
    assert "[APP] VS Code" in fusion
    assert "[TITLE] test.py" in fusion
    assert "[SCENE] coding" in fusion
    assert "[ACTION] typing" in fusion
    assert "[CAPTION] A code screenshot" in fusion
    assert "[KEYWORDS] python, code" in fusion
    assert "[OCR_HEAD] import os" in fusion

def test_query_parser_basic():
    """Test simple query parsing."""
    parser = QueryParser()
    query = "hello world"
    parsed = parser.parse(query)
    
    assert parsed.text == "hello world"
    assert parsed.start_time is None
    assert parsed.mandatory_keywords == []

def test_query_parser_quotes():
    """Test extraction of mandatory keywords in quotes."""
    parser = QueryParser()
    query = 'find "error 500" in logs'
    parsed = parser.parse(query)
    
    assert "error 500" in parsed.mandatory_keywords
    # Verify quotes are NOT removed from main text (depends on implementation, 
    # current implementation keeps them in text but extracts them to mandatory_keywords)
    # Actually looking at code: text = query.strip() ... doesn't remove quotes from text.
    assert parsed.text == 'find "error 500" in logs'

def test_query_parser_time_today():
    """Test 'today' filter."""
    parser = QueryParser()
    query = "what happened today"
    parsed = parser.parse(query)
    
    assert parsed.start_time is not None
    # 'today' should be removed from text
    assert "today" not in parsed.text.lower()
    
    # Check start_time is roughly today (start of day)
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day).timestamp()
    assert parsed.start_time == today_start

def test_query_parser_time_yesterday():
    """Test 'yesterday' filter."""
    parser = QueryParser()
    query = "yesterday meeting"
    parsed = parser.parse(query)
    
    assert parsed.start_time is not None
    assert parsed.end_time is not None
    assert parsed.end_time > parsed.start_time
    assert "yesterday" not in parsed.text.lower()
