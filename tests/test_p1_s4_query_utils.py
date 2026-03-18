"""Tests for query_utils.sanitize_fts5_query — P1-S4 Section 1.

Covers:
- Basic tokenization
- Special characters
- Empty/whitespace handling
- Quote handling
- Unicode support
- Mixed cases

Per tasks.md §1.2 and specs/fts-search/spec.md §Query normalization.
"""

import pytest

from openrecall.server.search.query_utils import sanitize_fts5_query


class TestSanitizeFts5QueryBasic:
    """Basic tokenization tests."""

    def test_two_words(self):
        """hello world → "hello" "world"."""
        assert sanitize_fts5_query("hello world") == '"hello" "world"'

    def test_ip_address(self):
        """100.100.0.42 → "100.100.0.42" (preserves dots)."""
        assert sanitize_fts5_query("100.100.0.42") == '"100.100.0.42"'

    def test_parentheses(self):
        """foo(bar) → "foo(bar)" (preserves parens, not interpreted as FTS5 operators)."""
        assert sanitize_fts5_query("foo(bar)") == '"foo(bar)"'

    def test_plus_sign(self):
        """C++ → "C++" (preserves plus signs)."""
        assert sanitize_fts5_query("C++") == '"C++"'

    def test_single_word(self):
        """Single word is quoted."""
        assert sanitize_fts5_query("hello") == '"hello"'

    def test_three_words(self):
        """Multiple words are each quoted."""
        assert sanitize_fts5_query("foo bar baz") == '"foo" "bar" "baz"'


class TestSanitizeFts5QueryEmptyWhitespace:
    """Empty/whitespace handling."""

    def test_empty_string(self):
        """Empty string → empty string."""
        assert sanitize_fts5_query("") == ""

    def test_single_space(self):
        """Single space → empty string."""
        assert sanitize_fts5_query(" ") == ""

    def test_multiple_spaces(self):
        """Multiple spaces → empty string."""
        assert sanitize_fts5_query("   ") == ""

    def test_tabs_and_newlines(self):
        """Tabs and newlines are whitespace."""
        assert sanitize_fts5_query("\t\n  \r\n") == ""

    def test_leading_trailing_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        assert sanitize_fts5_query("  hello world  ") == '"hello" "world"'


class TestSanitizeFts5QueryQuotes:
    """Quote handling."""

    def test_internal_double_quote(self):
        """foo"bar → "foobar" (internal quotes stripped)."""
        assert sanitize_fts5_query('foo"bar') == '"foobar"'

    def test_only_quotes(self):
        """\"\"\" (only quotes) → empty string."""
        assert sanitize_fts5_query('"""') == ""

    def test_quoted_word(self):
        """"hello" → "hello" (existing quotes normalized)."""
        assert sanitize_fts5_query('"hello"') == '"hello"'

    def test_mixed_quotes(self):
        """Mixed quotes are stripped from tokens."""
        assert sanitize_fts5_query('foo "bar" baz') == '"foo" "bar" "baz"'

    def test_multiple_internal_quotes(self):
        """Multiple internal quotes are all stripped."""
        assert sanitize_fts5_query('a"b"c') == '"abc"'


class TestSanitizeFts5QueryUnicode:
    """Unicode support."""

    def test_chinese(self):
        """你好世界 → "你好世界"."""
        assert sanitize_fts5_query("你好世界") == '"你好世界"'

    def test_chinese_with_special_chars(self):
        """C++ 编程 → "C++" "编程"."""
        assert sanitize_fts5_query("C++ 编程") == '"C++" "编程"'

    def test_japanese(self):
        """Japanese text is preserved."""
        assert sanitize_fts5_query("こんにちは") == '"こんにちは"'

    def test_emoji(self):
        """Emoji are preserved (though rare in OCR)."""
        assert sanitize_fts5_query("hello 👋") == '"hello" "👋"'


class TestSanitizeFts5QueryMixed:
    """Mixed cases."""

    def test_parens_and_quotes(self):
        """foo(bar) "test" → "foo(bar)" "test"."""
        assert sanitize_fts5_query('foo(bar) "test"') == '"foo(bar)" "test"'

    def test_url_like(self):
        """URL-like strings are preserved as single tokens."""
        assert sanitize_fts5_query("https://example.com") == '"https://example.com"'

    def test_path_like(self):
        """File paths are preserved as single tokens."""
        assert sanitize_fts5_query("/usr/local/bin") == '"/usr/local/bin"'

    def test_email_like(self):
        """Email-like strings are preserved as single tokens."""
        assert sanitize_fts5_query("user@example.com") == '"user@example.com"'

    def test_dash_preserved(self):
        """Dashes are preserved in tokens."""
        assert sanitize_fts5_query("foo-bar") == '"foo-bar"'

    def test_underscore_preserved(self):
        """Underscores are preserved in tokens."""
        assert sanitize_fts5_query("foo_bar_baz") == '"foo_bar_baz"'

    def test_asterisk_preserved_for_prefix_match(self):
        """Asterisks are preserved inside quotes (aligns with screenpipe sanitize_fts5_query).

        Note: For prefix matching, users should use expand_search_query or append *
        after the closing quote. sanitize_fts5_query preserves * as literal text.
        """
        # test* becomes "test*" - asterisk is preserved inside quotes
        result = sanitize_fts5_query("test*")
        assert result == '"test*"'

    def test_asterisk_in_middle_preserved(self):
        """Asterisk in middle of token is preserved."""
        result = sanitize_fts5_query("foo*bar")
        assert result == '"foo*bar"'


class TestSanitizeFts5QuerySecurity:
    """Security-related tests (FTS5 operator injection prevention)."""

    def test_fts5_operators_neutralized(self):
        """FTS5 operators (AND, OR, NOT) are quoted, not interpreted."""
        # These should be treated as literal words, not operators
        assert sanitize_fts5_query("AND OR NOT") == '"AND" "OR" "NOT"'

    def test_caret_preserved(self):
        """Caret (FTS5 NEAR operator) is preserved (aligns with screenpipe)."""
        # foo^bar should become "foo^bar" - user can construct NEAR queries
        result = sanitize_fts5_query("foo^bar")
        assert result == '"foo^bar"'

    def test_asterisk_preserved_inside_quotes(self):
        """Asterisk is preserved inside quotes (aligns with screenpipe sanitize_fts5_query)."""
        # sanitize_fts5_query("test*") -> "test*" (asterisk inside quotes)
        result = sanitize_fts5_query("test*")
        assert result == '"test*"'
        # For actual prefix matching in FTS5, the pattern is "term"* (asterisk outside quotes)
        # But sanitize_fts5_query doesn't do that - use expand_search_query for prefix matching

    def test_column_filter_not_interpreted(self):
        """Column filter syntax is not interpreted as FTS5 column filter."""
        # app_name:test should be quoted, not interpreted as column:term
        assert sanitize_fts5_query("app_name:test") == '"app_name:test"'

    def test_near_operator_not_interpreted(self):
        """NEAR operator is quoted as literal."""
        result = sanitize_fts5_query("NEAR(test)")
        assert result == '"NEAR(test)"'
