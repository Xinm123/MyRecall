"""Persistent local buffer for offline resilience.

Provides a thread-safe, file-system-backed queue mechanism that ensures
zero data loss even when the server is unavailable.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BufferItem:
    """Represents an item in the buffer queue.
    
    Attributes:
        id: Unique identifier for the buffer item.
        image_path: Path to the .webp image file.
        metadata: Dictionary containing timestamp, active_app, active_window, etc.
    """
    id: str
    image_path: Path
    metadata: Dict[str, Any]


class LocalBuffer:
    """Thread-safe, file-system-backed queue for screenshot buffering.
    
    Uses atomic write pattern (.tmp -> rename) to ensure data integrity.
    Files are only deleted after confirmed upload to server.
    
    Attributes:
        storage_dir: Directory for storing buffered files.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize the buffer.
        
        Args:
            storage_dir: Directory for buffer storage. Defaults to settings.buffer_path.
        """
        self.storage_dir = storage_dir or settings.buffer_path
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def enqueue(self, image: Image.Image, metadata: Dict[str, Any]) -> str:
        """Add an image and metadata to the buffer queue.
        
        Uses atomic write pattern:
        1. Save image to {id}.webp
        2. Write metadata to {id}.json.tmp
        3. Rename {id}.json.tmp -> {id}.json (atomic commit)
        
        Args:
            image: PIL Image to buffer.
            metadata: Dictionary with timestamp, active_app, active_window, etc.
            
        Returns:
            The unique ID of the buffered item.
        """
        # Generate unique ID: timestamp + uuid for uniqueness
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique_id = f"{timestamp_str}_{uuid.uuid4().hex[:8]}"
        
        image_path = self.storage_dir / f"{unique_id}.webp"
        meta_tmp_path = self.storage_dir / f"{unique_id}.json.tmp"
        meta_path = self.storage_dir / f"{unique_id}.json"
        
        # Step 1: Save image
        image.save(str(image_path), format="webp", lossless=True)
        
        # Step 2: Prepare metadata (convert non-serializable types)
        serializable_meta = self._serialize_metadata(metadata)
        
        # Step 3: Write to temp file
        with open(meta_tmp_path, "w", encoding="utf-8") as f:
            json.dump(serializable_meta, f, ensure_ascii=False, indent=2)
        
        # Step 4: Atomic commit via rename
        os.rename(meta_tmp_path, meta_path)
        
        app_name = metadata.get("active_app", "Unknown")
        buffer_count = self.count()
        logger.info(f"📥 Buffered: {app_name} | Queue: {buffer_count} items")
        return unique_id
    
    def _serialize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert metadata values to JSON-serializable types.
        
        Args:
            metadata: Original metadata dictionary.
            
        Returns:
            Dictionary with all values converted to serializable types.
        """
        result = {}
        for key, value in metadata.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, Path):
                result[key] = str(value)
            else:
                result[key] = value
        return result
    
    def get_next_batch(self, limit: int = 1) -> List[BufferItem]:
        """Get the next batch of items from the buffer (FIFO order).
        
        Scans for .json files, validates corresponding .webp exists,
        and returns items sorted by filename (oldest first).
        
        Args:
            limit: Maximum number of items to return.
            
        Returns:
            List of BufferItem objects. Does NOT load images into memory.
        """
        items: List[BufferItem] = []
        
        # Scan for .json files (not .json.tmp - those are incomplete)
        json_files = sorted(self.storage_dir.glob("*.json"))
        
        for json_path in json_files[:limit * 2]:  # Check extra in case of orphans
            if len(items) >= limit:
                break
                
            item_id = json_path.stem  # filename without extension
            image_path = self.storage_dir / f"{item_id}.webp"
            
            # Validate: corresponding image must exist
            if not image_path.exists():
                logger.warning(f"Orphan metadata found (no image): {json_path}")
                # Clean up orphan
                try:
                    json_path.unlink()
                except OSError as e:
                    logger.error(f"Failed to delete orphan: {e}")
                continue
            
            # Load metadata
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Failed to read metadata {json_path}: {e}")
                continue
            
            items.append(BufferItem(
                id=item_id,
                image_path=image_path,
                metadata=metadata,
            ))
        
        return items
    
    def commit(self, file_ids: List[str]) -> None:
        """Delete successfully uploaded items from the buffer.
        
        Called after server confirms successful upload.
        
        Args:
            file_ids: List of item IDs to remove.
        """
        for item_id in file_ids:
            image_path = self.storage_dir / f"{item_id}.webp"
            meta_path = self.storage_dir / f"{item_id}.json"
            
            deleted = False
            for path in [image_path, meta_path]:
                try:
                    if path.exists():
                        path.unlink()
                        deleted = True
                except OSError as e:
                    logger.error(f"Failed to delete {path}: {e}")
            
            if deleted:
                remaining = self.count()
                logger.info(f"✅ Committed: {item_id[:20]}... | Remaining: {remaining} items")
    
    def count(self) -> int:
        """Get the number of items currently in the buffer.
        
        Returns:
            Number of complete (json + webp) items in buffer.
        """
        return len(list(self.storage_dir.glob("*.json")))
    
    def clear(self) -> None:
        """Clear all items from the buffer. Use with caution."""
        for path in self.storage_dir.glob("*"):
            try:
                path.unlink()
            except OSError as e:
                logger.error(f"Failed to delete {path}: {e}")


# Module-level singleton
_buffer: Optional[LocalBuffer] = None


def get_buffer() -> LocalBuffer:
    """Get or create the global LocalBuffer instance.
    
    Returns:
        The global LocalBuffer instance.
    """
    global _buffer
    if _buffer is None:
        _buffer = LocalBuffer()
    return _buffer
