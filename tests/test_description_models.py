import pytest
from pydantic import ValidationError
from openrecall.server.description.models import FrameDescription, FrameContext


def test_frame_description_new_fields():
    """Test FrameDescription accepts narrative, summary, tags."""
    # Create a narrative that is within 1024 characters (54 chars * 18 = 972)
    narrative = ("This is a detailed description of the screen content. " * 18).rstrip()
    assert len(narrative) <= 1024
    desc = FrameDescription(
        narrative=narrative,
        summary="Brief summary of activity",
        tags=["github", "coding", "browsing"]
    )
    assert len(desc.narrative) <= 1024
    assert len(desc.summary) <= 256
    assert 3 <= len(desc.tags) <= 8


def test_frame_description_ignores_old_fields():
    """Test FrameDescription ignores entities and intent (extra='ignore' behavior)."""
    # Pydantic BaseModel by default ignores extra fields
    desc = FrameDescription(
        narrative="test",
        summary="test",
        tags=["tag1"],
        entities=["entity1"],  # extra field - ignored
        intent="intent"  # extra field - ignored
    )
    assert desc.narrative == "test"
    assert desc.summary == "test"
    assert desc.tags == ["tag1"]
    # entities and intent are not stored
    assert not hasattr(desc, 'entities')
    assert not hasattr(desc, 'intent')


def test_frame_description_tags_validation():
    """Test tags length validation - too many tags raises error."""
    # Too many tags should raise validation error (max_length=10)
    with pytest.raises(ValidationError):
        FrameDescription(
            narrative="test",
            summary="test",
            tags=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"]  # 12 tags
        )


def test_frame_description_tags_at_max():
    """Test tags at exactly max length (10)."""
    desc = FrameDescription(
        narrative="test",
        summary="test",
        tags=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]  # 10 tags
    )
    assert len(desc.tags) == 10


def test_frame_description_tags_lowercase():
    """Test tags are converted to lowercase."""
    desc = FrameDescription(
        narrative="test",
        summary="test",
        tags=["GitHub", "CODING", "Browsing"]
    )
    assert desc.tags == ["github", "coding", "browsing"]


def test_frame_description_tags_strips_whitespace():
    """Test tags have whitespace stripped."""
    desc = FrameDescription(
        narrative="test",
        summary="test",
        tags=["  github  ", "  coding  ", "  browsing  "]
    )
    assert desc.tags == ["github", "coding", "browsing"]


def test_frame_description_tags_filters_empty():
    """Test empty tags are filtered out."""
    desc = FrameDescription(
        narrative="test",
        summary="test",
        tags=["github", "", "  ", "coding"]
    )
    assert desc.tags == ["github", "coding"]


def test_frame_description_to_db_dict():
    """Test to_db_dict returns correct fields."""
    desc = FrameDescription(
        narrative="Detailed narrative",
        summary="Brief summary",
        tags=["tag1", "tag2"]
    )
    db_dict = desc.to_db_dict()
    assert "narrative" in db_dict
    assert "summary" in db_dict
    assert "tags_json" in db_dict
    assert "entities_json" not in db_dict
    assert "intent" not in db_dict
    import json
    assert json.loads(db_dict["tags_json"]) == ["tag1", "tag2"]


def test_frame_description_narrative_max_length():
    """Test narrative max length is 1024."""
    long_narrative = "x" * 1025
    with pytest.raises(ValidationError):
        FrameDescription(
            narrative=long_narrative,
            summary="test",
            tags=["tag1", "tag2", "tag3"]
        )


def test_frame_description_summary_max_length():
    """Test summary max length is 256."""
    long_summary = "x" * 257
    with pytest.raises(ValidationError):
        FrameDescription(
            narrative="test",
            summary=long_summary,
            tags=["tag1", "tag2", "tag3"]
        )
