# openrecall/server/database/embedding_store.py
"""LanceDB store for frame embeddings."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import lancedb
import numpy as np
from lancedb.pydantic import LanceModel, Vector
from pydantic import Field

from openrecall.server.embedding.models import FrameEmbedding

logger = logging.getLogger(__name__)


class FrameEmbeddingSchema(LanceModel):
    """LanceDB schema for frame embeddings."""

    frame_id: int = Field(description="Reference to frames.id")
    embedding_vector: Vector(1024) = Field(
        description="Multimodal embedding vector"
    )
    embedding_model: str = Field(
        default="qwen3-vl-embedding",
        description="Model used to generate embedding",
    )
    timestamp: str = Field(description="Frame timestamp (ISO8601 UTC)")
    app_name: str = Field(default="", description="Application name")
    window_name: str = Field(default="", description="Window title")


class EmbeddingStore:
    """LanceDB storage for frame embeddings."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        table_name: str = "frame_embeddings",
    ):
        """Initialize the embedding store.

        Args:
            db_path: Path to LanceDB database. Defaults to settings.lancedb_path.
            table_name: Table name for embeddings.
        """
        from openrecall.shared.config import settings

        self.db_path = Path(db_path or settings.lancedb_path)
        self.table_name = table_name

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db = lancedb.connect(str(self.db_path))
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the table with schema if it doesn't exist."""
        existing_tables = self.db.list_tables()

        if self.table_name not in existing_tables:
            logger.info(f"Creating LanceDB table '{self.table_name}'")
            try:
                self.db.create_table(
                    self.table_name, schema=FrameEmbeddingSchema
                )
            except ValueError as e:
                if "already exists" in str(e):
                    pass
                else:
                    raise
        else:
            # Table exists, validate by opening
            try:
                self.db.open_table(self.table_name)
            except Exception as e:
                logger.warning(
                    f"Schema mismatch for table '{self.table_name}': {e}"
                )
                logger.warning("Dropping and recreating table...")
                self.db.drop_table(self.table_name)
                self.db.create_table(
                    self.table_name, schema=FrameEmbeddingSchema
                )

    def save_embedding(self, embedding: FrameEmbedding) -> None:
        """Save a frame embedding to the store.

        Args:
            embedding: FrameEmbedding to save
        """
        table = self.db.open_table(self.table_name)

        # Check if embedding already exists for this frame
        existing = self.get_by_frame_id(embedding.frame_id)
        if existing is not None:
            # Delete existing embedding
            table.delete(f"frame_id = {embedding.frame_id}")

        # Add new embedding
        table.add([embedding.to_storage_dict()])
        logger.debug(f"Saved embedding for frame_id={embedding.frame_id}")

    def search(
        self,
        query_vector: List[float],
        limit: int = 20,
    ) -> List[FrameEmbedding]:
        """Search for similar embeddings.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results

        Returns:
            List of FrameEmbedding sorted by similarity (highest first)
        """
        table = self.db.open_table(self.table_name)

        query = table.search(query_vector)

        # Try to use cosine metric if available
        metric_fn = getattr(query, "metric", None)
        if callable(metric_fn):
            try:
                query = query.metric("cosine")
            except Exception:
                pass

        results = query.limit(limit).to_list()

        # Convert to FrameEmbedding objects
        embeddings = []
        for r in results:
            emb = FrameEmbedding(
                frame_id=r["frame_id"],
                embedding_vector=r["embedding_vector"],
                embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
                timestamp=r["timestamp"],
                app_name=r.get("app_name", ""),
                window_name=r.get("window_name", ""),
            )
            embeddings.append(emb)

        return embeddings

    def get_by_frame_id(self, frame_id: int) -> Optional[FrameEmbedding]:
        """Get embedding by frame_id.

        Args:
            frame_id: Frame ID to look up

        Returns:
            FrameEmbedding if found, None otherwise
        """
        table = self.db.open_table(self.table_name)

        results = table.search().where(f"frame_id = {frame_id}").limit(1).to_list()

        if not results:
            return None

        r = results[0]
        return FrameEmbedding(
            frame_id=r["frame_id"],
            embedding_vector=r["embedding_vector"],
            embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
            timestamp=r["timestamp"],
            app_name=r.get("app_name", ""),
            window_name=r.get("window_name", ""),
        )

    def delete_by_frame_id(self, frame_id: int) -> None:
        """Delete embedding by frame_id.

        Args:
            frame_id: Frame ID to delete
        """
        table = self.db.open_table(self.table_name)
        table.delete(f"frame_id = {frame_id}")
        logger.debug(f"Deleted embedding for frame_id={frame_id}")

    def count(self) -> int:
        """Return total number of embeddings."""
        table = self.db.open_table(self.table_name)
        return len(table)

    def search_with_distance(
        self,
        query_vector: List[float],
        limit: int = 20,
    ) -> List[Tuple[FrameEmbedding, float]]:
        """Search for similar embeddings and return with distance scores.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results

        Returns:
            List of (FrameEmbedding, distance) tuples sorted by distance (ascending)
        """
        table = self.db.open_table(self.table_name)

        query = table.search(query_vector)

        # Try to use cosine metric if available
        metric_fn = getattr(query, "metric", None)
        if callable(metric_fn):
            try:
                query = query.metric("cosine")
            except Exception:
                pass

        # Get results with distance column
        results = query.limit(limit).to_list()

        # Convert to (FrameEmbedding, distance) tuples
        embeddings_with_distance = []
        for r in results:
            emb = FrameEmbedding(
                frame_id=r["frame_id"],
                embedding_vector=r["embedding_vector"],
                embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
                timestamp=r["timestamp"],
                app_name=r.get("app_name", ""),
                window_name=r.get("window_name", ""),
            )
            # LanceDB returns distance in _distance column
            distance = r.get("_distance", 0.0)
            embeddings_with_distance.append((emb, distance))

        return embeddings_with_distance
