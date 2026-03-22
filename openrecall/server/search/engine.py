"""FTS5-only Search Engine for P1-S4.

This module replaces the v2 hybrid search with a pure FTS5 implementation:
- Dynamic SQL builder with conditional JOINs
- BM25 ranking when query present
- Metadata filtering via frames_fts
- Time range and text length filtering
- Pagination with COUNT

Per data-model.md §3.0.3 and specs/fts-search/spec.md.
"""

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from openrecall.server.search.query_utils import sanitize_fts5_query
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _sanitize_fts_value(value: str) -> str:
    """Sanitize a value for use in FTS5 column filter expressions.

    Strips double-quotes to prevent FTS5 MATCH syntax errors.
    This is NOT for SQL injection prevention - FTS5 MATCH expressions
    are parsed separately from SQL. It prevents syntax errors when
    user input contains quotes.

    Args:
        value: Raw user input string

    Returns:
        Sanitized string safe for FTS5 column:value syntax.
    """
    if not value:
        return ""
    # Strip double-quotes to prevent breaking FTS5 MATCH syntax
    return value.replace('"', "")


@dataclass
class SearchParams:
    """Parameters for search operations."""

    q: str = ""
    limit: int = 20
    offset: int = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    app_name: Optional[str] = None
    window_name: Optional[str] = None
    focused: Optional[bool] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    browser_url: Optional[str] = None
    content_type: str = "all"  # "ocr", "accessibility", or "all"


@dataclass
class SearchResult:
    """A single search result item."""

    frame_id: int
    timestamp: str
    text: str
    app_name: Optional[str]
    window_name: Optional[str]
    browser_url: Optional[str]  # Reserved, always null in P1
    focused: Optional[bool]
    device_name: str
    file_path: str
    frame_url: str
    tags: list[str]  # Reserved, always empty in P1


class SearchEngine:
    """FTS5-only search engine for OCR text with metadata filtering.

    Per data-model.md §3.0.3 JOIN strategy:
    - frames INNER JOIN ocr_text (always)
    - frames_fts JOIN (when metadata filters present)
    - ocr_text_fts JOIN (when q non-empty)

    Uses GROUP BY frames.id to prevent JOIN explosion.
    """

    # Pagination limits
    DEFAULT_LIMIT = 20
    MAX_LIMIT = 100

    # COUNT query latency warning threshold (ms)
    COUNT_WARNING_THRESHOLD_MS = 500

    def __init__(
        self,
        db_path: Optional[Path] = None,
        frames_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the search engine.

        Args:
            db_path: Path to edge.db. Defaults to settings.db_path.
            frames_dir: Path to frames directory. Defaults to settings.frames_dir.
        """
        self.db_path = db_path or settings.db_path
        self.frames_dir = frames_dir or settings.frames_dir

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _build_query(
        self, params: SearchParams, is_count: bool = False
    ) -> tuple[str, list[Any]]:
        """Build the SQL query with dynamic JOINs.

        Args:
            params: Search parameters
            is_count: If True, build COUNT query; otherwise SELECT

        Returns:
            Tuple of (SQL string, parameters list)
        """
        # Determine which JOINs are needed
        has_text_query = bool(params.q and params.q.strip())
        has_metadata_filters = bool(
            params.app_name or params.window_name or params.focused is not None
        )

        # Base tables
        if is_count:
            select_clause = "SELECT COUNT(DISTINCT frames.id) AS total"
        else:
            select_clause = """
                SELECT frames.id AS frame_id,
                       frames.timestamp,
                       ocr_text.text,
                       frames.app_name,
                       frames.window_name,
                       frames.browser_url,
                       frames.focused,
                       frames.device_name,
                       frames.text_source"""
            # Include FTS rank when text query present
            if has_text_query:
                select_clause += (
                    ",\n                       ocr_text_fts.rank AS fts_rank"
                )
            else:
                select_clause += ",\n                       NULL AS fts_rank"

        # Always join frames with ocr_text
        from_clause = "FROM frames INNER JOIN ocr_text ON frames.id = ocr_text.frame_id"

        # Conditional JOINs
        join_clauses = []
        where_clauses = ["frames.status = 'completed'"]
        params_list: list[Any] = []

        # JOIN frames_fts when metadata filters present
        if has_metadata_filters:
            join_clauses.append("INNER JOIN frames_fts ON frames.id = frames_fts.id")

        # JOIN ocr_text_fts when text query present
        if has_text_query:
            join_clauses.append(
                "INNER JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id"
            )

        # Build FTS MATCH clauses
        fts_match_parts = []

        if has_text_query:
            sanitized_q = sanitize_fts5_query(params.q)
            fts_match_parts.append(f"ocr_text_fts MATCH ?")
            params_list.append(sanitized_q)

        if has_metadata_filters:
            frames_fts_parts = []
            if params.app_name:
                safe_app = _sanitize_fts_value(params.app_name)
                frames_fts_parts.append(f'app_name:"{safe_app}"')
            if params.window_name:
                safe_window = _sanitize_fts_value(params.window_name)
                frames_fts_parts.append(f'window_name:"{safe_window}"')
            if params.focused is not None:
                focused_val = 1 if params.focused else 0
                frames_fts_parts.append(f"focused:{focused_val}")

            if frames_fts_parts:
                fts_match_parts.append(f"frames_fts MATCH ?")
                params_list.append(" ".join(frames_fts_parts))

        if fts_match_parts:
            where_clauses.append(f"({' AND '.join(fts_match_parts)})")

        # Time range filtering
        if params.start_time:
            where_clauses.append("frames.timestamp >= ?")
            params_list.append(params.start_time)
        if params.end_time:
            where_clauses.append("frames.timestamp <= ?")
            params_list.append(params.end_time)

        # Text length filtering
        if params.min_length is not None:
            where_clauses.append("ocr_text.text_length >= ?")
            params_list.append(params.min_length)
        if params.max_length is not None:
            where_clauses.append("ocr_text.text_length <= ?")
            params_list.append(params.max_length)

        # Build the full query
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        sql_parts.append("WHERE " + " AND ".join(where_clauses))

        if not is_count:
            # GROUP BY to prevent JOIN explosion
            sql_parts.append("GROUP BY frames.id")

            # ORDER BY
            if has_text_query:
                # BM25 rank when query present
                sql_parts.append("ORDER BY ocr_text_fts.rank, frames.timestamp DESC")
            else:
                # Timestamp DESC when browsing
                sql_parts.append("ORDER BY frames.timestamp DESC")

            # Pagination
            limit = min(max(1, params.limit), self.MAX_LIMIT)
            offset = max(0, params.offset)
            sql_parts.append(f"LIMIT {limit} OFFSET {offset}")

        sql = "\n".join(sql_parts)
        return sql, params_list

    def search(
        self,
        q: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
        content_type: str = "all",
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute FTS5 search with metadata filtering.

        Args:
            q: Text query (sanitized via sanitize_fts5_query)
            limit: Max results (clamped to 1-100)
            offset: Pagination offset
            start_time: ISO8601 UTC start timestamp
            end_time: ISO8601 UTC end timestamp
            app_name: Filter by app name (exact match via FTS)
            window_name: Filter by window name (exact match via FTS)
            focused: Filter by focused state
            min_length: Minimum OCR text length
            max_length: Maximum OCR text length
            browser_url: Filter by browser URL
            content_type: "ocr", "accessibility", or "all" (default: "all")

        Returns:
            Tuple of (results list, total count)
        """
        # Normalize content_type
        content_type = content_type.strip().lower() if content_type else "all"
        if content_type not in ("ocr", "accessibility", "all"):
            content_type = "all"

        if content_type == "ocr":
            return self._search_ocr(
                q=q,
                limit=limit,
                offset=offset,
                start_time=start_time,
                end_time=end_time,
                app_name=app_name,
                window_name=window_name,
                focused=focused,
                min_length=min_length,
                max_length=max_length,
                browser_url=browser_url,
            )
        elif content_type == "accessibility":
            return self._search_accessibility(
                q=q,
                limit=limit,
                offset=offset,
                start_time=start_time,
                end_time=end_time,
                app_name=app_name,
                window_name=window_name,
                focused=focused,
                min_length=min_length,
                max_length=max_length,
                browser_url=browser_url,
            )
        else:
            return self._search_all(
                q=q,
                limit=limit,
                offset=offset,
                start_time=start_time,
                end_time=end_time,
                app_name=app_name,
                window_name=window_name,
                focused=focused,
                min_length=min_length,
                max_length=max_length,
                browser_url=browser_url,
            )

    def _search_ocr(
        self,
        q: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search OCR-canonical frames (text_source='ocr').

        Uses ocr_text_fts for text search and frames_fts for metadata filtering.
        """
        start_ts = time.perf_counter()

        params = SearchParams(
            q=q,
            limit=limit,
            offset=offset,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
            browser_url=browser_url,
            content_type="ocr",
        )

        results = []
        total = 0

        try:
            with self._connect() as conn:
                # Execute search query
                sql, sql_params = self._build_ocr_query(params, is_count=False)
                rows = conn.execute(sql, sql_params).fetchall()

                for row in rows:
                    frame_id = row["frame_id"]
                    ts = row["timestamp"]

                    result = {
                        "frame_id": frame_id,
                        "timestamp": ts,
                        "text": row["text"] or "",
                        "text_source": "ocr",
                        "app_name": row["app_name"],
                        "window_name": row["window_name"],
                        "browser_url": row["browser_url"],
                        "focused": bool(row["focused"])
                        if row["focused"] is not None
                        else None,
                        "device_name": row["device_name"] or "monitor_0",
                        "file_path": f"{ts}.jpg",
                        "frame_url": f"/v1/frames/{frame_id}",
                        "tags": [],  # Reserved, always empty in P1
                        "fts_rank": float(row["fts_rank"])
                        if row["fts_rank"] is not None
                        else None,
                    }
                    results.append(result)

                # Execute count query
                count_sql, count_params = self._build_ocr_query(params, is_count=True)
                count_start = time.perf_counter()
                count_row = conn.execute(count_sql, count_params).fetchone()
                count_elapsed_ms = (time.perf_counter() - count_start) * 1000.0

                total = count_row["total"] if count_row else 0

                # Log COUNT latency warning if exceeds threshold
                if count_elapsed_ms > self.COUNT_WARNING_THRESHOLD_MS:
                    logger.warning(
                        "MRV3 count_latency_warning count_ms=%.1f q='%s' content_type=ocr",
                        count_elapsed_ms,
                        q[:50] if q else "",
                    )

        except sqlite3.Error as e:
            logger.error("OCR search failed: %s", e)
            return [], 0

        # Log latency
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        query_type = "standard" if q else "browse"
        logger.info(
            "MRV3 search_latency_ms=%.1f query_type=%s q_present=%s limit=%d offset=%d total=%d content_type=ocr",
            elapsed_ms,
            query_type,
            bool(q),
            params.limit,
            params.offset,
            total,
        )

        return results, total

    def _build_ocr_query(
        self, params: SearchParams, is_count: bool = False
    ) -> tuple[str, list[Any]]:
        """Build SQL query for OCR-canonical frames.

        Filters: frames.text_source='ocr'
        FTS: ocr_text_fts for text, frames_fts for metadata + browser_url
        """
        has_text_query = bool(params.q and params.q.strip())
        has_metadata_filters = bool(
            params.app_name or params.window_name or params.focused is not None or params.browser_url
        )

        if is_count:
            select_clause = "SELECT COUNT(DISTINCT frames.id) AS total"
        else:
            select_clause = """
                SELECT frames.id AS frame_id,
                       frames.timestamp,
                       ocr_text.text,
                       frames.app_name,
                       frames.window_name,
                       frames.browser_url,
                       frames.focused,
                       frames.device_name,
                       frames.text_source"""
            if has_text_query:
                select_clause += ",\n                       ocr_text_fts.rank AS fts_rank"
            else:
                select_clause += ",\n                       NULL AS fts_rank"

        from_clause = "FROM frames INNER JOIN ocr_text ON frames.id = ocr_text.frame_id"

        join_clauses = []
        where_clauses = ["frames.status = 'completed'", "frames.text_source = 'ocr'"]
        params_list: list[Any] = []

        if has_metadata_filters:
            join_clauses.append("INNER JOIN frames_fts ON frames.id = frames_fts.id")

        if has_text_query:
            join_clauses.append(
                "INNER JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id"
            )

        # Build FTS MATCH clauses
        fts_match_parts = []

        if has_text_query:
            sanitized_q = sanitize_fts5_query(params.q)
            fts_match_parts.append("ocr_text_fts MATCH ?")
            params_list.append(sanitized_q)

        if has_metadata_filters:
            frames_fts_parts = []
            if params.app_name:
                safe_app = _sanitize_fts_value(params.app_name)
                frames_fts_parts.append(f'app_name:"{safe_app}"')
            if params.window_name:
                safe_window = _sanitize_fts_value(params.window_name)
                frames_fts_parts.append(f'window_name:"{safe_window}"')
            if params.focused is not None:
                focused_val = 1 if params.focused else 0
                frames_fts_parts.append(f"focused:{focused_val}")
            if params.browser_url:
                safe_url = _sanitize_fts_value(params.browser_url)
                frames_fts_parts.append(f'browser_url:"{safe_url}"')

            if frames_fts_parts:
                fts_match_parts.append("frames_fts MATCH ?")
                params_list.append(" ".join(frames_fts_parts))

        if fts_match_parts:
            where_clauses.append(f"({' AND '.join(fts_match_parts)})")

        # Time range filtering
        if params.start_time:
            where_clauses.append("frames.timestamp >= ?")
            params_list.append(params.start_time)
        if params.end_time:
            where_clauses.append("frames.timestamp <= ?")
            params_list.append(params.end_time)

        # Text length filtering
        if params.min_length is not None:
            where_clauses.append("ocr_text.text_length >= ?")
            params_list.append(params.min_length)
        if params.max_length is not None:
            where_clauses.append("ocr_text.text_length <= ?")
            params_list.append(params.max_length)

        # Build the full query
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        sql_parts.append("WHERE " + " AND ".join(where_clauses))

        if not is_count:
            sql_parts.append("GROUP BY frames.id")

            if has_text_query:
                sql_parts.append("ORDER BY ocr_text_fts.rank, frames.timestamp DESC")
            else:
                sql_parts.append("ORDER BY frames.timestamp DESC")

            limit = min(max(1, params.limit), self.MAX_LIMIT)
            offset = max(0, params.offset)
            sql_parts.append(f"LIMIT {limit} OFFSET {offset}")

        sql = "\n".join(sql_parts)
        return sql, params_list

    def _search_accessibility(
        self,
        q: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search accessibility-canonical frames (text_source='accessibility').

        Uses accessibility_fts for text and metadata search.
        """
        start_ts = time.perf_counter()

        params = SearchParams(
            q=q,
            limit=limit,
            offset=offset,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
            browser_url=browser_url,
            content_type="accessibility",
        )

        results = []
        total = 0

        try:
            with self._connect() as conn:
                # Execute search query
                sql, sql_params = self._build_accessibility_query(params, is_count=False)
                rows = conn.execute(sql, sql_params).fetchall()

                for row in rows:
                    frame_id = row["frame_id"]
                    ts = row["timestamp"]

                    result = {
                        "frame_id": frame_id,
                        "timestamp": ts,
                        "text": row["text_content"] or "",
                        "text_source": "accessibility",
                        "app_name": row["app_name"],
                        "window_name": row["window_name"],
                        "browser_url": row["browser_url"],
                        "focused": bool(row["focused"])
                        if row["focused"] is not None
                        else None,
                        "device_name": row["device_name"] or "monitor_0",
                        "file_path": f"{ts}.jpg",
                        "frame_url": f"/v1/frames/{frame_id}",
                        "tags": [],  # Reserved, always empty in P1
                        "fts_rank": float(row["fts_rank"])
                        if row["fts_rank"] is not None
                        else None,
                    }
                    results.append(result)

                # Execute count query
                count_sql, count_params = self._build_accessibility_query(params, is_count=True)
                count_start = time.perf_counter()
                count_row = conn.execute(count_sql, count_params).fetchone()
                count_elapsed_ms = (time.perf_counter() - count_start) * 1000.0

                total = count_row["total"] if count_row else 0

                if count_elapsed_ms > self.COUNT_WARNING_THRESHOLD_MS:
                    logger.warning(
                        "MRV3 count_latency_warning count_ms=%.1f q='%s' content_type=accessibility",
                        count_elapsed_ms,
                        q[:50] if q else "",
                    )

        except sqlite3.Error as e:
            logger.error("Accessibility search failed: %s", e)
            return [], 0

        # Log latency
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        query_type = "standard" if q else "browse"
        logger.info(
            "MRV3 search_latency_ms=%.1f query_type=%s q_present=%s limit=%d offset=%d total=%d content_type=accessibility",
            elapsed_ms,
            query_type,
            bool(q),
            params.limit,
            params.offset,
            total,
        )

        return results, total

    def _build_accessibility_query(
        self, params: SearchParams, is_count: bool = False
    ) -> tuple[str, list[Any]]:
        """Build SQL query for accessibility-canonical frames.

        Filters: frames.text_source='accessibility'
        FTS: accessibility_fts for text_content, app_name, window_name, browser_url
        """
        has_text_query = bool(params.q and params.q.strip())
        has_filters = bool(
            params.app_name or params.window_name or params.browser_url or params.focused is not None
        )

        if is_count:
            select_clause = "SELECT COUNT(DISTINCT frames.id) AS total"
        else:
            select_clause = """
                SELECT frames.id AS frame_id,
                       frames.timestamp,
                       accessibility.text_content,
                       accessibility.app_name,
                       accessibility.window_name,
                       accessibility.browser_url,
                       frames.focused,
                       frames.device_name,
                       frames.text_source"""
            # Only return fts_rank when there's an actual text query for relevance scoring
            # Metadata-only filtering doesn't produce meaningful BM25 ranks
            if has_text_query:
                select_clause += ",\n                       accessibility_fts.rank AS fts_rank"
            else:
                select_clause += ",\n                       NULL AS fts_rank"

        from_clause = """FROM frames
            INNER JOIN accessibility ON frames.id = accessibility.frame_id"""

        join_clauses = []
        where_clauses = ["frames.status = 'completed'", "frames.text_source = 'accessibility'"]
        params_list: list[Any] = []

        # Always join accessibility_fts when we have filters or text query
        if has_text_query or has_filters:
            join_clauses.append(
                "INNER JOIN accessibility_fts ON accessibility.id = accessibility_fts.rowid"
            )

        # Build FTS MATCH clause
        if has_text_query or has_filters:
            fts_parts = []

            if has_text_query:
                sanitized_q = sanitize_fts5_query(params.q)
                fts_parts.append(f"({sanitized_q})")

            if params.app_name:
                safe_app = _sanitize_fts_value(params.app_name)
                fts_parts.append(f'app_name:"{safe_app}"')
            if params.window_name:
                safe_window = _sanitize_fts_value(params.window_name)
                fts_parts.append(f'window_name:"{safe_window}"')
            if params.browser_url:
                safe_url = _sanitize_fts_value(params.browser_url)
                fts_parts.append(f'browser_url:"{safe_url}"')

            if fts_parts:
                where_clauses.append(f"accessibility_fts MATCH ?")
                params_list.append(" ".join(fts_parts))

        # focused filter (not in accessibility_fts, filter directly)
        if params.focused is not None:
            where_clauses.append("frames.focused = ?")
            params_list.append(1 if params.focused else 0)

        # Time range filtering
        if params.start_time:
            where_clauses.append("frames.timestamp >= ?")
            params_list.append(params.start_time)
        if params.end_time:
            where_clauses.append("frames.timestamp <= ?")
            params_list.append(params.end_time)

        # Text length filtering
        if params.min_length is not None:
            where_clauses.append("accessibility.text_length >= ?")
            params_list.append(params.min_length)
        if params.max_length is not None:
            where_clauses.append("accessibility.text_length <= ?")
            params_list.append(params.max_length)

        # Build the full query
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        sql_parts.append("WHERE " + " AND ".join(where_clauses))

        if not is_count:
            sql_parts.append("GROUP BY frames.id")

            # Only order by FTS rank when there's an actual text query
            # Metadata-only filtering doesn't produce meaningful BM25 ranks
            if has_text_query:
                sql_parts.append("ORDER BY accessibility_fts.rank, frames.timestamp DESC")
            else:
                sql_parts.append("ORDER BY frames.timestamp DESC")

            limit = min(max(1, params.limit), self.MAX_LIMIT)
            offset = max(0, params.offset)
            sql_parts.append(f"LIMIT {limit} OFFSET {offset}")

        sql = "\n".join(sql_parts)
        return sql, params_list

    def _search_all(
        self,
        q: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search both OCR and accessibility frames, merge results.

        Per mvp.md:
        - Fetch limit + offset candidates from each sub-search with offset=0
        - Merge results
        - Deduplicate by frame_id
        - Sort globally by timestamp DESC
        - Apply pagination after merge
        - Total count is sum of counts from both sources (since no overlap)
        """
        start_ts = time.perf_counter()

        # Clamp limit like other search methods
        limit = min(max(1, limit), self.MAX_LIMIT)
        offset = max(0, offset)

        # Fetch enough rows from each source for the global window
        fetch_limit = limit + offset

        # Fetch from both sources with offset=0, getting counts too
        ocr_results, ocr_total = self._search_ocr(
            q=q,
            limit=fetch_limit,
            offset=0,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
            browser_url=browser_url,
        )

        ax_results, ax_total = self._search_accessibility(
            q=q,
            limit=fetch_limit,
            offset=0,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
            browser_url=browser_url,
        )

        # Merge and deduplicate by frame_id
        merged = []
        seen_ids = set()
        for r in ocr_results + ax_results:
            fid = r.get("frame_id")
            if fid not in seen_ids:
                seen_ids.add(fid)
                merged.append(r)

        # Sort globally by timestamp DESC
        merged.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Apply pagination after merge
        paginated = merged[offset:offset + limit]

        # Total is the sum of counts from both sources
        # (OCR and accessibility frames are mutually exclusive per text_source)
        total = ocr_total + ax_total

        # Log latency
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        query_type = "standard" if q else "browse"
        logger.info(
            "MRV3 search_latency_ms=%.1f query_type=%s q_present=%s limit=%d offset=%d total=%d content_type=all",
            elapsed_ms,
            query_type,
            bool(q),
            limit,
            offset,
            total,
        )

        return paginated, total

    def count(
        self,
        q: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> int:
        """Count matching frames without returning results.

        Args:
            Same as search() except limit/offset

        Returns:
            Total count of matching frames
        """
        params = SearchParams(
            q=q,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
        )

        try:
            with self._connect() as conn:
                sql, sql_params = self._build_query(params, is_count=True)
                row = conn.execute(sql, sql_params).fetchone()
                return row["total"] if row else 0
        except sqlite3.Error as e:
            logger.error("Count failed: %s", e)
            return 0
