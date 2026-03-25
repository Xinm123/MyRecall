"""Unified FTS5 Search Engine for P1-S4.

After FTS unification, there is a single `frames_fts` table with `full_text` column.
This module provides a single query path that queries `frames` JOIN `frames_fts`.

Per spec: docs/superpowers/specs/2026-03-25-fts-unification-design.md
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
    content_type: str = "all"  # Deprecated, accepted but ignored


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
    """Unified FTS5 search engine using frames_fts with full_text.

    After FTS unification:
    - Single `frames_fts` table indexes `frames.full_text` + metadata
    - Single query path: `frames INNER JOIN frames_fts`
    - content_type parameter accepted but ignored (deprecated)

    Per spec: docs/superpowers/specs/2026-03-25-fts-unification-design.md
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

    def _build_where_clause(
        self, params: SearchParams
    ) -> tuple[str, list[Any]]:
        """Build WHERE clause and parameters for frames JOIN frames_fts query.

        Shared helper used by both _build_query and count_by_type to avoid
        duplicating the filter-building logic.

        Args:
            params: Search parameters

        Returns:
            Tuple of (WHERE clause string, parameters list)
        """
        has_text_query = bool(params.q and params.q.strip())
        where_parts = ["frames.status = 'completed'", "frames.full_text IS NOT NULL"]
        params_list: list[Any] = []

        if has_text_query:
            sanitized_q = sanitize_fts5_query(params.q)
            where_parts.append("frames_fts MATCH ?")
            params_list.append(sanitized_q)

        metadata_parts = []
        if params.app_name:
            safe_app = _sanitize_fts_value(params.app_name)
            metadata_parts.append(f'app_name:"{safe_app}"')
        if params.window_name:
            safe_window = _sanitize_fts_value(params.window_name)
            metadata_parts.append(f'window_name:"{safe_window}"')
        if params.browser_url:
            safe_url = _sanitize_fts_value(params.browser_url)
            metadata_parts.append(f'browser_url:"{safe_url}"')

        if metadata_parts:
            where_parts.append("frames_fts MATCH ?")
            params_list.append(" ".join(metadata_parts))

        if params.focused is not None:
            where_parts.append("frames.focused = ?")
            params_list.append(1 if params.focused else 0)

        if params.start_time:
            where_parts.append("frames.timestamp >= ?")
            params_list.append(params.start_time)
        if params.end_time:
            where_parts.append("frames.timestamp <= ?")
            params_list.append(params.end_time)

        if params.min_length is not None:
            where_parts.append("LENGTH(frames.full_text) >= ?")
            params_list.append(params.min_length)
        if params.max_length is not None:
            where_parts.append("LENGTH(frames.full_text) <= ?")
            params_list.append(params.max_length)

        return " AND ".join(where_parts), params_list

    def _build_query(
        self, params: SearchParams, is_count: bool = False
    ) -> tuple[str, list[Any]]:
        """Build unified SQL query against frames JOIN frames_fts.

        Uses `frames.full_text` for text search, indexed via `frames_fts`.

        Args:
            params: Search parameters
            is_count: If True, build COUNT query; otherwise SELECT

        Returns:
            Tuple of (SQL string, parameters list)
        """
        has_text_query = bool(params.q and params.q.strip())

        if is_count:
            select_clause = "SELECT COUNT(DISTINCT frames.id) AS total"
        else:
            select_clause = """
                SELECT frames.id AS frame_id,
                       frames.timestamp,
                       frames.full_text,
                       frames.app_name,
                       frames.window_name,
                       frames.browser_url,
                       frames.focused,
                       frames.device_name,
                       frames.text_source"""
            if has_text_query:
                select_clause += ",\n                       frames_fts.rank AS fts_rank"
            else:
                select_clause += ",\n                       NULL AS fts_rank"

        from_clause = "FROM frames"
        join_clauses = ["INNER JOIN frames_fts ON frames.id = frames_fts.id"]

        where_clause, params_list = self._build_where_clause(params)

        # Build the full query
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        sql_parts.append("WHERE " + where_clause)

        if not is_count:
            sql_parts.append("GROUP BY frames.id")

            if has_text_query:
                sql_parts.append("ORDER BY frames_fts.rank, frames.timestamp DESC")
            else:
                sql_parts.append("ORDER BY frames.timestamp DESC")

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
        """Execute unified FTS5 search.

        After FTS unification, content_type is accepted but ignored.
        All frames with full_text are searched via the single frames_fts table.

        Args:
            q: Text query (sanitized via sanitize_fts5_query)
            limit: Max results (clamped to 1-100)
            offset: Pagination offset
            start_time: ISO8601 UTC start timestamp
            end_time: ISO8601 UTC end timestamp
            app_name: Filter by app name (exact match via FTS)
            window_name: Filter by window name (exact match via FTS)
            focused: Filter by focused state
            min_length: Minimum full_text length
            max_length: Maximum full_text length
            browser_url: Filter by browser URL
            content_type: Deprecated, accepted but ignored

        Returns:
            Tuple of (results list, total count)
        """
        # Normalize content_type (deprecated, ignored)
        content_type = content_type.strip().lower() if content_type else "all"
        if content_type not in ("ocr", "accessibility", "all"):
            content_type = "all"

        # Log deprecation warning for non-default content_type
        if content_type != "all" and settings.debug:
            logger.debug(
                "content_type parameter is deprecated and ignored. "
                "All content is now searched via unified frames_fts. q='%s'",
                q[:50] if q else "",
            )

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
            content_type=content_type,
        )

        results = []
        total = 0

        try:
            with self._connect() as conn:
                # Execute search query
                sql, sql_params = self._build_query(params, is_count=False)
                rows = conn.execute(sql, sql_params).fetchall()

                for row in rows:
                    frame_id = row["frame_id"]
                    ts = row["timestamp"]

                    result = {
                        "frame_id": frame_id,
                        "timestamp": ts,
                        "text": row["full_text"] or "",
                        "text_source": row["text_source"],
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
                count_sql, count_params = self._build_query(params, is_count=True)
                count_start = time.perf_counter()
                count_row = conn.execute(count_sql, count_params).fetchone()
                count_elapsed_ms = (time.perf_counter() - count_start) * 1000.0

                total = count_row["total"] if count_row else 0

                if count_elapsed_ms > self.COUNT_WARNING_THRESHOLD_MS:
                    logger.warning(
                        "MRV3 count_latency_warning count_ms=%.1f q='%s'",
                        count_elapsed_ms,
                        q[:50] if q else "",
                    )

        except sqlite3.Error as e:
            logger.error("Unified search failed: %s", e)
            return [], 0

        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        query_type = "standard" if q else "browse"
        logger.info(
            "MRV3 search_latency_ms=%.1f query_type=%s q_present=%s limit=%d offset=%d total=%d",
            elapsed_ms,
            query_type,
            bool(q),
            params.limit,
            params.offset,
            total,
        )

        return results, total

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

    def count_by_type(
        self,
        q: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
    ) -> dict[str, int]:
        """Count matching frames by text_source.

        After FTS unification, content_type is not filterable via FTS.
        This method groups results by frames.text_source for API compatibility.

        Args:
            Same as search() except limit/offset/content_type

        Returns:
            Dict with "ocr" and "accessibility" counts
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
            browser_url=browser_url,
        )

        try:
            with self._connect() as conn:
                where_clause, query_params = self._build_where_clause(params)

                # Count by text_source
                sql = f"""
                    SELECT frames.text_source, COUNT(DISTINCT frames.id) AS cnt
                    FROM frames
                    INNER JOIN frames_fts ON frames.id = frames_fts.id
                    WHERE {where_clause}
                    GROUP BY frames.text_source
                """
                rows = conn.execute(sql, query_params).fetchall()

                result = {"ocr": 0, "accessibility": 0}
                for row in rows:
                    source = row["text_source"] or "ocr"
                    if source in result:
                        result[source] = row["cnt"]
                    else:
                        # Handle 'hybrid' or other text_source values
                        pass

                return result
        except sqlite3.Error as e:
            logger.error("Count by type failed: %s", e)
            return {"ocr": 0, "accessibility": 0}
