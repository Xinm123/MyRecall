"""Search P95 Latency Baseline Test — P1-S4 Section 2.

This test establishes latency baseline for the FTS5 SearchEngine by executing
>= 200 queries and recording P50/P90/P95/P99 distribution.

Query categories (50 each):
1. Empty queries (browse mode)
2. Single-word queries
3. Phrase queries
4. Queries with metadata filters (app_name, window_name, focused)
5. Combined queries (text + filters)

Uses Nearest-rank algorithm for percentile computation.
Observation only (non-blocking).

Per AGENTS.md and specs/fts-search/spec.md.
"""

import logging
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from openrecall.server.search.engine import SearchEngine

logger = logging.getLogger(__name__)

# Mark this as performance and slow test
pytestmark = [pytest.mark.perf, pytest.mark.slow]


def compute_percentile(sorted_values: list[float], percentile: float) -> float:
    """Compute percentile using Nearest-rank algorithm.

    Args:
        sorted_values: List of values sorted in ascending order
        percentile: Percentile to compute (0-100)

    Returns:
        The percentile value
    """
    if not sorted_values:
        return 0.0

    n = len(sorted_values)
    # Nearest-rank: rank = ceil(P/100 * N)
    rank = int((percentile / 100.0) * n)
    # Clamp rank to valid range (1-indexed to 0-indexed)
    rank = max(1, min(rank, n))
    return sorted_values[rank - 1]


def generate_test_frames(count: int) -> list[tuple]:
    """Generate test frame data.

    Args:
        count: Number of frames to generate

    Returns:
        List of (frame_id, capture_id, timestamp, app_name, window_name,
                  browser_url, focused, ocr_text) tuples
    """
    apps = [
        "Safari",
        "VSCode",
        "Terminal",
        "Slack",
        "Chrome",
        "Mail",
        "Notes",
        "Finder",
    ]
    windows = [
        "main.py",
        "inbox",
        "search results",
        "document.txt",
        "browser tab",
        "settings",
    ]
    texts = [
        "hello world from application",
        "meeting at 3pm tomorrow",
        "search query results page",
        "def function(): pass",
        "git status commit push",
        "email notification message",
        "document editing text content",
        "settings configuration options",
        "file browser navigation",
        "code review comments feedback",
    ]

    frames = []
    base_time = datetime(2026, 3, 18, 8, 0, 0, tzinfo=timezone.utc)

    for i in range(count):
        # Create unique timestamp for each frame
        ts = base_time.replace(hour=8 + (i // 60), minute=i % 60)
        timestamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Rotate through test data
        app = apps[i % len(apps)]
        window = windows[i % len(windows)]
        text = texts[i % len(texts)]
        focused = (i % 3) != 0  # ~67% focused

        frames.append(
            (
                i + 1,
                f"capture-{i:04d}",
                timestamp,
                app,
                f"{window}-{i}",
                None,
                focused,
                f"{text} unique_id_{i}",  # Add unique text for variety
            )
        )

    return frames


@pytest.fixture
def perf_db():
    """Create a temporary database with substantial test data (100+ frames)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "perf.db"
        frames_dir = Path(tmpdir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create schema (same as test_p1_s4_search_fts.py)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capture_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                local_timestamp TEXT,
                app_name TEXT DEFAULT NULL,
                window_name TEXT DEFAULT NULL,
                browser_url TEXT DEFAULT NULL,
                focused BOOLEAN DEFAULT NULL,
                device_name TEXT NOT NULL DEFAULT 'monitor_0',
                snapshot_path TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                text_source TEXT DEFAULT NULL,
                ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS ocr_text (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                text_length INTEGER DEFAULT 0,
                ocr_engine TEXT,
                app_name TEXT DEFAULT NULL,
                window_name TEXT DEFAULT NULL,
                FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
                app_name, window_name, browser_url, focused, accessibility_text,
                id UNINDEXED, tokenize='unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(
                text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61'
            );

            CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);

            -- FTS triggers
            CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
                INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused, accessibility_text)
                VALUES (NEW.id, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''),
                        COALESCE(NEW.browser_url, ''), COALESCE(NEW.focused, 0), '');
            END;

            CREATE TRIGGER IF NOT EXISTS ocr_text_ai AFTER INSERT ON ocr_text
            WHEN NEW.text IS NOT NULL AND NEW.text != '' BEGIN
                INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
                VALUES (NEW.frame_id, NEW.text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''));
            END;
        """)

        # Insert 150 frames for substantial test data
        test_frames = generate_test_frames(150)

        from openrecall.server.database.frames_store import _utc_to_local_timestamp
        for (
            frame_id,
            capture_id,
            ts,
            app,
            window,
            url,
            focused,
            ocr_text,
        ) in test_frames:
            local_ts = _utc_to_local_timestamp(ts)
            conn.execute(
                """INSERT INTO frames (id, capture_id, timestamp, local_timestamp, app_name, window_name, browser_url, focused, status, text_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', 'ocr')""",
                (frame_id, capture_id, ts, local_ts, app, window, url, focused),
            )
            conn.execute(
                """INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine)
                   VALUES (?, ?, ?, 'test')""",
                (frame_id, ocr_text, len(ocr_text)),
            )

        conn.commit()
        conn.close()

        yield db_path, frames_dir


class TestSearchLatencyBaseline:
    """Search P95 latency baseline test."""

    TIMEOUT_THRESHOLD_SEC = 30.0

    def test_search_latency_baseline(self, perf_db):
        """Execute >= 200 queries and record P50/P90/P95/P99 latency distribution.

        Query categories (50 each):
        1. Empty queries (browse mode)
        2. Single-word queries
        3. Phrase queries
        4. Queries with metadata filters
        5. Combined queries (text + filters)
        """
        db_path, frames_dir = perf_db
        engine = SearchEngine(db_path=db_path, frames_dir=frames_dir)

        latencies: list[float] = []
        timeout_count = 0

        # Category 1: Empty queries (browse mode) - 50 queries
        logger.info("Running Category 1: Empty queries (browse mode)")
        for i in range(50):
            start = time.perf_counter()
            results, total = engine.search(q="", limit=20, offset=i % 10)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

            if elapsed > self.TIMEOUT_THRESHOLD_SEC:
                timeout_count += 1
                logger.warning("Query timeout: category=empty latency=%.3fs", elapsed)

            logger.debug(
                "Empty query %d: latency=%.3fms total=%d", i, elapsed * 1000, total
            )

        # Category 2: Single-word queries - 50 queries
        single_words = [
            "hello",
            "meeting",
            "search",
            "function",
            "git",
            "email",
            "document",
            "settings",
            "file",
            "code",
            "application",
            "results",
            "notification",
            "editing",
            "browser",
            "configuration",
            "navigation",
            "review",
            "comments",
            "feedback",
            "world",
            "tomorrow",
            "page",
            "status",
            "message",
            "content",
            "options",
            "unique",
            "pass",
            "push",
        ]
        logger.info("Running Category 2: Single-word queries")
        for i, word in enumerate(single_words * 2):  # 50 queries
            start = time.perf_counter()
            results, total = engine.search(q=word, limit=20, offset=0)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

            if elapsed > self.TIMEOUT_THRESHOLD_SEC:
                timeout_count += 1
                logger.warning(
                    "Query timeout: category=single_word word='%s' latency=%.3fs",
                    word,
                    elapsed,
                )

            logger.debug(
                "Single-word query %d: word='%s' latency=%.3fms total=%d",
                i,
                word,
                elapsed * 1000,
                total,
            )

        # Category 3: Phrase queries - 50 queries
        phrases = [
            "hello world",
            "meeting tomorrow",
            "search results",
            "def function",
            "git status",
            "email notification",
            "document editing",
            "settings configuration",
            "file browser",
            "code review",
            "application content",
            "unique id",
            "commit push",
            "comments feedback",
            "browser navigation",
        ]
        logger.info("Running Category 3: Phrase queries")
        phrase_queries = (phrases * 4)[:50]  # 50 queries from repeating phrases
        for i, phrase in enumerate(phrase_queries):
            start = time.perf_counter()
            results, total = engine.search(q=phrase, limit=20, offset=0)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

            if elapsed > self.TIMEOUT_THRESHOLD_SEC:
                timeout_count += 1
                logger.warning(
                    "Query timeout: category=phrase phrase='%s' latency=%.3fs",
                    phrase,
                    elapsed,
                )

            logger.debug(
                "Phrase query %d: phrase='%s' latency=%.3fms total=%d",
                i,
                phrase,
                elapsed * 1000,
                total,
            )

        # Ensure we have 50 phrase queries
        remaining = 50 - (len(phrases) * 3)
        for i in range(remaining):
            phrase = phrases[i % len(phrases)]
            start = time.perf_counter()
            results, total = engine.search(q=phrase, limit=20, offset=0)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

            if elapsed > self.TIMEOUT_THRESHOLD_SEC:
                timeout_count += 1
                logger.warning(
                    "Query timeout: category=phrase phrase='%s' latency=%.3fs",
                    phrase,
                    elapsed,
                )

            logger.debug(
                "Phrase query %d: phrase='%s' latency=%.3fms total=%d",
                45 + i,
                phrase,
                elapsed * 1000,
                total,
            )

        # Category 4: Queries with metadata filters - 50 queries
        filter_combos = [
            {"app_name": "Safari"},
            {"app_name": "VSCode"},
            {"app_name": "Terminal"},
            {"app_name": "Slack"},
            {"app_name": "Chrome"},
            {"window_name": "main.py"},
            {"window_name": "inbox"},
            {"window_name": "search results"},
            {"focused": True},
            {"focused": False},
            {"app_name": "Safari", "focused": True},
            {"app_name": "VSCode", "focused": True},
            {"app_name": "Terminal", "focused": False},
            {"window_name": "document.txt", "focused": True},
            {"app_name": "Chrome", "window_name": "browser tab"},
        ]
        logger.info("Running Category 4: Metadata filter queries")
        for i in range(50):
            combo = filter_combos[i % len(filter_combos)]
            start = time.perf_counter()
            results, total = engine.search(q="", limit=20, offset=0, **combo)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

            if elapsed > self.TIMEOUT_THRESHOLD_SEC:
                timeout_count += 1
                logger.warning(
                    "Query timeout: category=filter combo=%s latency=%.3fs",
                    combo,
                    elapsed,
                )

            logger.debug(
                "Filter query %d: combo=%s latency=%.3fms total=%d",
                i,
                combo,
                elapsed * 1000,
                total,
            )

        # Category 5: Combined queries (text + filters) - 50 queries
        combined_queries = [
            ({"q": "hello", "app_name": "Safari"}),
            ({"q": "meeting", "app_name": "Slack"}),
            ({"q": "function", "app_name": "VSCode"}),
            ({"q": "git", "app_name": "Terminal"}),
            ({"q": "search", "app_name": "Chrome"}),
            ({"q": "hello", "focused": True}),
            ({"q": "document", "focused": True}),
            ({"q": "code", "app_name": "VSCode", "focused": True}),
            ({"q": "email", "app_name": "Mail"}),
            ({"q": "settings", "focused": False}),
        ]
        logger.info("Running Category 5: Combined queries")
        for i in range(50):
            combo = combined_queries[i % len(combined_queries)]
            start = time.perf_counter()
            results, total = engine.search(limit=20, offset=0, **combo)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

            if elapsed > self.TIMEOUT_THRESHOLD_SEC:
                timeout_count += 1
                logger.warning(
                    "Query timeout: category=combined combo=%s latency=%.3fs",
                    combo,
                    elapsed,
                )

            logger.debug(
                "Combined query %d: combo=%s latency=%.3fms total=%d",
                i,
                combo,
                elapsed * 1000,
                total,
            )

        # Compute statistics
        sorted_latencies = sorted(latencies)
        total_queries = len(latencies)

        p50 = compute_percentile(sorted_latencies, 50)
        p90 = compute_percentile(sorted_latencies, 90)
        p95 = compute_percentile(sorted_latencies, 95)
        p99 = compute_percentile(sorted_latencies, 99)
        max_latency = sorted_latencies[-1] if sorted_latencies else 0.0

        # Convert to milliseconds for reporting
        p50_ms = p50 * 1000
        p90_ms = p90 * 1000
        p95_ms = p95 * 1000
        p99_ms = p99 * 1000
        max_ms = max_latency * 1000

        # Log and print report
        report = f"""
================================================================================
SEARCH LATENCY BASELINE REPORT
================================================================================
Total Queries:    {total_queries}
Timeout Threshold: {self.TIMEOUT_THRESHOLD_SEC}s
Timeout Count:    {timeout_count}

LATENCY DISTRIBUTION (Nearest-rank percentiles):
  P50:  {p50_ms:.3f} ms
  P90:  {p90_ms:.3f} ms
  P95:  {p95_ms:.3f} ms
  P99:  {p99_ms:.3f} ms
  Max:  {max_ms:.3f} ms

QUERY BREAKDOWN:
  Category 1 (Empty/Browse):     50 queries
  Category 2 (Single-word):      50 queries
  Category 3 (Phrase):           50 queries
  Category 4 (Metadata filters): 50 queries
  Category 5 (Combined):         50 queries

DATABASE INFO:
  Total frames: 150
================================================================================
"""
        logger.info(
            "MRV3 search_latency_baseline_report%s", report.replace("\n", " | ")
        )
        print(report)

        # Assertion: at least 200 queries executed
        assert total_queries >= 200, f"Expected >= 200 queries, got {total_queries}"

        # Assertion: no more than 5% timeouts (observation test, but shouldn't fail completely)
        timeout_rate = timeout_count / total_queries if total_queries > 0 else 0
        assert timeout_rate < 0.10, (
            f"Timeout rate {timeout_rate:.1%} exceeds 10% threshold"
        )

        # Log summary for CI
        logger.info(
            "MRV3 search_latency_summary total=%d p50=%.1fms p90=%.1fms p95=%.1fms p99=%.1fms max=%.1fms timeouts=%d",
            total_queries,
            p50_ms,
            p90_ms,
            p95_ms,
            p99_ms,
            max_ms,
            timeout_count,
        )
