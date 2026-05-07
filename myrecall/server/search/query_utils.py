"""FTS5 query utilities for P1-S4 search.

This module provides:
- sanitize_fts5_query: Normalize user input for safe FTS5 MATCH queries

Per data-model.md §3.0.3 and specs/fts-search/spec.md.

Aligned with screenpipe text_normalizer::sanitize_fts5_query behavior.
"""


def sanitize_fts5_query(query: str) -> str:
    """Sanitize user input for FTS5 MATCH queries.

    Wraps each whitespace-delimited token in double quotes so that
    special characters (dots, parens, colons, etc.) are treated as
    literal text rather than FTS5 operators.

    This aligns with screenpipe's sanitize_fts5_query implementation:
    - Strips internal double-quotes (prevents unbalanced quotes)
    - Preserves asterisk (*) for FTS5 prefix matching
    - Preserves caret (^) for FTS5 NEAR operator

    Args:
        query: Raw user input string

    Returns:
        Sanitized query string suitable for FTS5 MATCH clause.
        Returns empty string for empty/whitespace-only input.

    Examples:
        >>> sanitize_fts5_query("hello world")
        '"hello" "world"'
        >>> sanitize_fts5_query("C++")
        '"C++"'
        >>> sanitize_fts5_query("test*")
        '"test*"'
        >>> sanitize_fts5_query('foo"bar')
        '"foobar"'
        >>> sanitize_fts5_query("")
        ''
    """
    if not query:
        return ""

    # Strip leading/trailing whitespace
    query = query.strip()
    if not query:
        return ""

    # Split by whitespace (handles tabs, newlines, multiple spaces)
    raw_tokens = query.split()

    # Process each token:
    # Strip internal double-quotes only (prevents unbalanced quotes)
    # Preserve * and ^ for FTS5 operators (prefix match, NEAR)
    tokens = []
    for token in raw_tokens:
        # Remove internal double-quotes only
        cleaned = token.replace('"', "")
        # Only add non-empty tokens
        if cleaned:
            tokens.append(cleaned)

    if not tokens:
        return ""

    # Wrap each token in double-quotes
    quoted_tokens = [f'"{token}"' for token in tokens]

    return " ".join(quoted_tokens)
