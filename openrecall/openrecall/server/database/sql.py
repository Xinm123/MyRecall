import logging
import sqlite3
from typing import List, Tuple

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

class FTSStore:
    def __init__(self):
        self.db_path = settings.fts_path
        self._init_db()

    def _init_db(self):
        """Initialize the FTS database and table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Create FTS5 virtual table
                # snapshot_id is UNINDEXED because we don't need full-text search on UUIDs
                conn.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts 
                       USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)"""
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize FTS database: {e}")
            raise

    def add_document(self, snapshot_id: str, ocr_text: str, caption: str, keywords: List[str]):
        """Add a document to the FTS index."""
        keywords_str = " ".join(keywords)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO ocr_fts (snapshot_id, ocr_text, caption, keywords) VALUES (?, ?, ?, ?)",
                    (str(snapshot_id), ocr_text, caption, keywords_str)
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to add document to FTS: {e}")

    def search(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        """Search for documents matching the query. Returns list of (snapshot_id, bm25_score)."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "SELECT snapshot_id, bm25(ocr_fts) AS score "
                    "FROM ocr_fts "
                    "WHERE ocr_fts MATCH ? "
                    "ORDER BY score ASC "
                    "LIMIT ?",
                    (query, limit),
                )
                return [(row[0], float(row[1])) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"FTS search failed: {e}")
            return []
