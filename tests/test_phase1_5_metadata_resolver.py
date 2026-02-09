"""Phase 1.5 tests: Metadata resolver — frame > chunk > null priority."""
import pytest

from openrecall.server.video.metadata_resolver import (
    ResolvedFrameMetadata,
    resolve_frame_metadata,
)


class TestResolveFrameMetadata:
    """Unit tests for resolve_frame_metadata() priority chain."""

    def test_frame_level_beats_chunk_level_app_name(self):
        """Frame-level app_name takes priority over chunk-level."""
        result = resolve_frame_metadata(
            frame_meta={"app_name": "FrameApp"},
            chunk_meta={"app_name": "ChunkApp"},
        )
        assert result.app_name == "FrameApp"

    def test_frame_level_beats_chunk_level_window_name(self):
        """Frame-level window_name takes priority over chunk-level."""
        result = resolve_frame_metadata(
            frame_meta={"window_name": "FrameWin"},
            chunk_meta={"window_name": "ChunkWin"},
        )
        assert result.window_name == "FrameWin"

    def test_chunk_level_used_when_frame_level_empty(self):
        """Chunk-level used when frame-level is empty string."""
        result = resolve_frame_metadata(
            frame_meta={"app_name": "", "window_name": ""},
            chunk_meta={"app_name": "ChunkApp", "window_name": "ChunkWin"},
        )
        assert result.app_name == "ChunkApp"
        assert result.window_name == "ChunkWin"

    def test_returns_none_when_both_empty(self):
        """Returns None when both frame and chunk are empty."""
        result = resolve_frame_metadata(
            frame_meta={"app_name": "", "window_name": ""},
            chunk_meta={"app_name": "", "window_name": ""},
        )
        assert result.app_name is None
        assert result.window_name is None

    def test_empty_string_treated_as_missing(self):
        """Empty string is treated as missing (returns None, not '')."""
        result = resolve_frame_metadata(
            frame_meta={"app_name": ""},
            chunk_meta={},
        )
        assert result.app_name is None

    def test_focused_none_when_not_provided(self):
        """focused is None when not in frame_meta."""
        result = resolve_frame_metadata(
            frame_meta={},
            chunk_meta={},
        )
        assert result.focused is None

    def test_focused_true_false_from_bool_and_int(self):
        """focused resolves correctly from bool and int inputs."""
        result_true = resolve_frame_metadata(
            frame_meta={"focused": True}, chunk_meta={},
        )
        assert result_true.focused is True

        result_false = resolve_frame_metadata(
            frame_meta={"focused": False}, chunk_meta={},
        )
        assert result_false.focused is False

        result_int_1 = resolve_frame_metadata(
            frame_meta={"focused": 1}, chunk_meta={},
        )
        assert result_int_1.focused is True

        result_int_0 = resolve_frame_metadata(
            frame_meta={"focused": 0}, chunk_meta={},
        )
        assert result_int_0.focused is False

    def test_focused_chunk_fallback_when_frame_missing(self):
        """focused falls back to chunk-level metadata when frame-level is missing."""
        result = resolve_frame_metadata(
            frame_meta={},
            chunk_meta={"focused": 1},
        )
        assert result.focused is True

    def test_browser_url_frame_then_chunk_fallback(self):
        """browser_url uses frame-level first, then chunk-level fallback."""
        result = resolve_frame_metadata(
            frame_meta={"browser_url": "https://example.com"},
            chunk_meta={},
        )
        assert result.browser_url == "https://example.com"

        # Chunk-level browser_url is used when frame-level is missing
        result_fallback = resolve_frame_metadata(
            frame_meta={},
            chunk_meta={"browser_url": "https://chunk.com"},
        )
        assert result_fallback.browser_url == "https://chunk.com"

    def test_source_field_correct(self):
        """Source field reflects actual resolution origin."""
        # frame source
        result_frame = resolve_frame_metadata(
            frame_meta={"app_name": "App"},
            chunk_meta={"app_name": "ChunkApp"},
        )
        assert result_frame.source == "frame"

        # chunk source
        result_chunk = resolve_frame_metadata(
            frame_meta={},
            chunk_meta={"app_name": "ChunkApp"},
        )
        assert result_chunk.source == "chunk"

        # none source
        result_none = resolve_frame_metadata(
            frame_meta={},
            chunk_meta={},
        )
        assert result_none.source == "none"

    def test_both_inputs_none_returns_all_none(self):
        """Both inputs None -> all fields are None."""
        result = resolve_frame_metadata(None, None)
        assert result.app_name is None
        assert result.window_name is None
        assert result.focused is None
        assert result.browser_url is None
        assert result.source == "none"

    def test_whitespace_only_strings_treated_as_missing(self):
        """Whitespace-only strings are treated as missing."""
        result = resolve_frame_metadata(
            frame_meta={"app_name": "   ", "window_name": "\t\n"},
            chunk_meta={"app_name": "ChunkApp"},
        )
        assert result.app_name == "ChunkApp"
        assert result.window_name is None
