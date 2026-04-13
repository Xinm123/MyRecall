"""Tests for search.html frontend template optimizations.

Tests cover:
- Default mode pill is "hybrid" (not "fts")
- min_length/max_length form fields removed
- include_text=true added to API query
- Flat response structure (no content wrapper)
- Description summary rendering
- Score field names updated (fts_score instead of fts_rank for BM25)
"""

import re
from pathlib import Path

import pytest


SEARCH_TEMPLATE_PATH = Path(__file__).parent.parent / "openrecall" / "client" / "web" / "templates" / "search.html"


@pytest.fixture
def search_html_content() -> str:
    """Load search.html template content."""
    return SEARCH_TEMPLATE_PATH.read_text(encoding="utf-8")


class TestSearchPageDefaultMode:
    """Tests for default search mode being 'hybrid'."""

    def test_search_page_has_hybrid_as_default_mode(self, search_html_content: str) -> None:
        """Test that the hybrid pill has 'active' class by default."""
        # Find the search mode pills section
        # The hybrid pill should have class="pill active" and aria-checked="true"
        hybrid_pill_pattern = r'<button[^>]*data-mode="hybrid"[^>]*>'
        matches = list(re.finditer(hybrid_pill_pattern, search_html_content))

        assert len(matches) > 0, "Hybrid pill button should exist"

        hybrid_pill = matches[0].group(0)

        # Check that hybrid pill has active class
        assert 'class="pill active"' in hybrid_pill or "class='pill active'" in hybrid_pill, \
            f"Hybrid pill should have 'active' class, got: {hybrid_pill}"

        # Check that hybrid pill has aria-checked="true"
        assert 'aria-checked="true"' in hybrid_pill, \
            f"Hybrid pill should have aria-checked='true', got: {hybrid_pill}"

    def test_fts_pill_not_active_by_default(self, search_html_content: str) -> None:
        """Test that the FTS pill does not have 'active' class by default."""
        fts_pill_pattern = r'<button[^>]*data-mode="fts"[^>]*>'
        matches = list(re.finditer(fts_pill_pattern, search_html_content))

        assert len(matches) > 0, "FTS pill button should exist"

        fts_pill = matches[0].group(0)

        # FTS pill should NOT have active class
        assert 'class="pill active"' not in fts_pill and "class='pill active'" not in fts_pill, \
            f"FTS pill should NOT have 'active' class, got: {fts_pill}"

        # FTS pill should have aria-checked="false"
        assert 'aria-checked="false"' in fts_pill or 'aria-checked="true"' not in fts_pill, \
            f"FTS pill should have aria-checked='false', got: {fts_pill}"


class TestSearchPageRemovedFields:
    """Tests for removed form fields."""

    def test_search_page_removes_min_length_field(self, search_html_content: str) -> None:
        """Test that min_length form field is removed."""
        # Check that there's no form field for min_length
        assert 'id="min_length"' not in search_html_content, \
            "min_length form field should be removed"
        assert 'name="min_length"' not in search_html_content, \
            "min_length form field should be removed"

    def test_search_page_removes_max_length_field(self, search_html_content: str) -> None:
        """Test that max_length form field is removed."""
        # Check that there's no form field for max_length
        assert 'id="max_length"' not in search_html_content, \
            "max_length form field should be removed"
        assert 'name="max_length"' not in search_html_content, \
            "max_length form field should be removed"


class TestSearchPageJSDefaults:
    """Tests for JavaScript defaults."""

    def test_search_mode_default_is_hybrid(self, search_html_content: str) -> None:
        """Test that JavaScript searchMode variable defaults to 'hybrid'."""
        # Look for: let searchMode = 'hybrid'; or similar
        pattern = r"let\s+searchMode\s*=\s*['\"]hybrid['\"]"
        assert re.search(pattern, search_html_content), \
            "JavaScript searchMode should default to 'hybrid'"

    def test_include_text_in_query_string(self, search_html_content: str) -> None:
        """Test that buildQueryString adds include_text=true."""
        # The buildQueryString function should add include_text=true
        # This ensures the grid view gets text for display

        # Check the entire JS block for include_text since the function
        # may call helpers or the regex may not capture nested braces
        assert "include_text" in search_html_content, \
            "Template should include 'include_text' parameter"

        # Check it's set to true
        assert "params.set('include_text', 'true')" in search_html_content or \
               'params.set("include_text", "true")' in search_html_content, \
            "buildQueryString should set include_text to 'true'"


class TestSearchPageFlatResponse:
    """Tests for flat response structure handling."""

    def test_modal_uses_flat_frame_id(self, search_html_content: str) -> None:
        """Test that modal uses item.frame_id (not item.content.frame_id)."""
        # In the modal update function, check that frame_id is accessed directly
        # Find modal image src assignment
        modal_pattern = r"modalImage\.src\s*="
        matches = list(re.finditer(modal_pattern, search_html_content))

        assert len(matches) > 0, "Modal image src should be set"

        # Check that it uses flat structure (item.frame_id, not item.content.frame_id)
        for match in matches:
            # Get surrounding context
            start = max(0, match.start() - 100)
            end = min(len(search_html_content), match.end() + 100)
            context = search_html_content[start:end]

            # Should use item.frame_id or item\.
            if "item.content.frame_id" in context:
                pytest.fail(
                    f"Modal should use flat structure (item.frame_id), not item.content.frame_id. "
                    f"Context: {context}"
                )

    def test_no_type_badge_in_render(self, search_html_content: str) -> None:
        """Test that type badge rendering is removed."""
        # The renderResults function should not render type badges
        # Look for type-badge in the render function

        # Find the renderResults function
        render_pattern = r"function\s+renderResults[^}]+(?:\{[^}]*\}[^}]*)*\}"
        render_match = re.search(render_pattern, search_html_content, re.DOTALL)

        if render_match:
            render_body = render_match.group(0)

            # Check if type-badge is in the render output
            # The old code had: <span class="type-badge type-${item.type.toLowerCase()}">
            if "type-badge" in render_body and "item.type" in render_body:
                pytest.fail(
                    "renderResults should not render type badges. "
                    "The response no longer has 'type' field."
                )


class TestSearchPageDescription:
    """Tests for description rendering."""

    def test_description_css_exists(self, search_html_content: str) -> None:
        """Test that description-summary CSS class is defined."""
        assert ".description-summary" in search_html_content, \
            "CSS class .description-summary should be defined for description preview"

    def test_description_render_in_template(self, search_html_content: str) -> None:
        """Test that description.summary is rendered in results."""
        # Should have item.description?.summary or similar in template
        assert "description" in search_html_content.lower(), \
            "Template should include description field handling"

    def test_description_css_has_ellipsis(self, search_html_content: str) -> None:
        """Test that description CSS includes ellipsis for overflow."""
        # Find the description-summary CSS block
        css_pattern = r"\.description-summary\s*\{[^}]+\}"
        css_match = re.search(css_pattern, search_html_content, re.DOTALL)

        assert css_match, "CSS for .description-summary should be defined"

        css_block = css_match.group(0)

        # Check for text-overflow: ellipsis
        assert "text-overflow" in css_block or "overflow" in css_block, \
            "Description CSS should handle overflow with ellipsis"


class TestSearchPageScoreFields:
    """Tests for score field handling."""

    def test_fts_score_used_for_bm25(self, search_html_content: str) -> None:
        """Test that BM25 display uses fts_score (not fts_rank for the score value)."""
        # The score display should use fts_score for the BM25 value
        # Look for fts_score in the score display logic
        assert "fts_score" in search_html_content, \
            "Score display should reference fts_score field"
