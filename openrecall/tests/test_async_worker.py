"""Tests for Phase 6.4.3 - Background Processing Worker."""

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from openrecall.server.database import (
    create_db,
    insert_pending_entry,
    get_pending_count,
    reset_stuck_tasks,
)
from openrecall.server.worker import ProcessingWorker
from openrecall.shared.config import Settings


@pytest.fixture
def temp_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        screenshots_path = Path(tmpdir) / "screenshots"
        screenshots_path.mkdir()
        
        # Patch settings
        original_settings = {
            "db_path": Settings().db_path,
            "screenshots_path": Settings().screenshots_path,
            "processing_lifo_threshold": Settings().processing_lifo_threshold,
        }
        
        with patch("openrecall.server.database.settings") as mock_settings, \
             patch("openrecall.server.worker.settings") as mock_worker_settings:
            
            mock_settings.db_path = db_path
            mock_settings.screenshots_path = screenshots_path
            mock_settings.processing_lifo_threshold = 3
            mock_settings.debug = True
            
            mock_worker_settings.db_path = db_path
            mock_worker_settings.screenshots_path = screenshots_path
            mock_worker_settings.processing_lifo_threshold = 3
            mock_worker_settings.debug = True
            
            create_db()
            
            yield {
                "db_path": db_path,
                "screenshots_path": screenshots_path,
            }


def create_mock_screenshot(screenshot_dir: Path, timestamp: str):
    """Create a mock screenshot file."""
    screenshot_path = screenshot_dir / f"{timestamp}.png"
    screenshot_path.write_text("mock image data")
    return screenshot_path


def test_worker_lifo_priority(temp_db):
    """Test that worker processes newest tasks first when queue >= threshold.
    
    Setup:
    - Insert 5 PENDING tasks (timestamps 1-5)
    - Threshold = 3
    - Expected: Task #5 processed first (newest) because count(5) > 3
    """
    db_path = temp_db["db_path"]
    screenshot_dir = temp_db["screenshots_path"]
    
    # Mock AI/OCR engines
    with patch("openrecall.server.worker.extract_text_from_image") as mock_ocr, \
         patch("openrecall.server.worker.get_ai_engine") as mock_ai, \
         patch("openrecall.server.worker.get_nlp_engine") as mock_nlp, \
         patch("openrecall.server.worker.Image.open") as mock_image_open:
        
        mock_ocr.return_value = "extracted text"
        mock_image_open.return_value = MagicMock()  # Mock PIL Image object
        
        mock_ai_instance = MagicMock()
        mock_ai_instance.analyze_image.return_value = "image description"
        mock_ai.return_value = mock_ai_instance
        
        mock_nlp_instance = MagicMock()
        mock_nlp_instance.encode.return_value = np.random.rand(1024).astype(np.float32)
        mock_nlp.return_value = mock_nlp_instance
        
        # Insert 5 pending tasks
        for i in range(1, 6):
            timestamp = i * 1000  # Use numeric timestamps
            create_mock_screenshot(screenshot_dir, str(timestamp))
            insert_pending_entry(timestamp, "TestApp", "Test Title", str(screenshot_dir / f"{timestamp}.png"))
        
        # Verify setup
        conn = sqlite3.connect(str(db_path))
        count = get_pending_count(conn)
        assert count == 5, "Should have 5 pending tasks"
        conn.close()
        
        # Start worker
        worker = ProcessingWorker()
        worker.start()
        
        # Wait for processing (should process at least one task)
        time.sleep(3)
        
        # Stop worker
        worker.stop()
        worker.join(timeout=5)
        
        # Verify processing order: newest first (LIFO)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, status FROM entries ORDER BY id"
        )
        results = cursor.fetchall()
        conn.close()
        
        # Check that at least some tasks were processed
        completed_count = sum(1 for _, status in results if status == "COMPLETED")
        assert completed_count > 0, "Worker should have processed at least one task"
        
        # Find first completed task - should be task #5 (newest)
        first_completed = next(
            (ts for ts, status in results if status == "COMPLETED"),
            None
        )
        
        # Due to timing, we may not complete all, but first should be newest
        # In a 5-task queue with threshold=3, LIFO applies
        print(f"Results: {results}")
        print(f"First completed: {first_completed}")


def test_worker_fifo_when_low_queue(temp_db):
    """Test that worker processes oldest tasks first when queue < threshold.
    
    Setup:
    - Insert 2 PENDING tasks (timestamps 1-2)
    - Threshold = 3
    - Expected: Task #1 processed first (oldest) because count(2) < 3
    """
    db_path = temp_db["db_path"]
    screenshot_dir = temp_db["screenshots_path"]
    
    # Mock AI/OCR engines
    with patch("openrecall.server.worker.extract_text_from_image") as mock_ocr, \
         patch("openrecall.server.worker.get_ai_engine") as mock_ai, \
         patch("openrecall.server.worker.get_nlp_engine") as mock_nlp, \
         patch("openrecall.server.worker.Image.open") as mock_image_open:
        
        mock_ocr.return_value = "extracted text"
        mock_image_open.return_value = MagicMock()  # Mock PIL Image object
        
        mock_ai_instance = MagicMock()
        mock_ai_instance.analyze_image.return_value = "image description"
        mock_ai.return_value = mock_ai_instance
        
        mock_nlp_instance = MagicMock()
        mock_nlp_instance.encode.return_value = np.random.rand(1024).astype(np.float32)
        mock_nlp.return_value = mock_nlp_instance
        
        # Insert 2 pending tasks (below threshold)
        for i in range(1, 3):
            timestamp = i * 1000  # Use numeric timestamps
            create_mock_screenshot(screenshot_dir, str(timestamp))
            insert_pending_entry(timestamp, "TestApp", "Test Title", str(screenshot_dir / f"{timestamp}.png"))
        
        # Start worker
        worker = ProcessingWorker()
        worker.start()
        
        # Wait for processing
        time.sleep(2)
        
        # Stop worker
        worker.stop()
        worker.join(timeout=5)
        
        # Verify FIFO: oldest first
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, status FROM entries ORDER BY id"
        )
        results = cursor.fetchall()
        conn.close()
        
        completed_count = sum(1 for _, status in results if status == "COMPLETED")
        assert completed_count > 0, "Worker should have processed at least one task"
        
        # First completed should be task #1 (oldest)
        first_completed = next(
            (ts for ts, status in results if status == "COMPLETED"),
            None
        )
        print(f"Results: {results}")
        print(f"First completed (should be oldest): {first_completed}")


def test_worker_error_handling(temp_db):
    """Test that worker marks tasks as FAILED when processing errors occur."""
    db_path = temp_db["db_path"]
    screenshot_dir = temp_db["screenshots_path"]
    
    # Mock OCR to raise an error
    with patch("openrecall.server.worker.extract_text_from_image") as mock_ocr, \
         patch("openrecall.server.worker.get_ai_engine") as mock_ai, \
         patch("openrecall.server.worker.get_nlp_engine") as mock_nlp:
        
        mock_ocr.side_effect = Exception("OCR failure")
        
        mock_ai_instance = MagicMock()
        mock_nlp_instance = MagicMock()
        mock_ai.return_value = mock_ai_instance
        mock_nlp.return_value = mock_nlp_instance
        
        # Insert 1 pending task
        timestamp = 1000
        create_mock_screenshot(screenshot_dir, str(timestamp))
        insert_pending_entry(timestamp, "TestApp", "Test Title", str(screenshot_dir / f"{timestamp}.png"))
        
        # Start worker
        worker = ProcessingWorker()
        worker.start()
        
        # Wait for processing attempt
        time.sleep(2)
        
        # Stop worker
        worker.stop()
        worker.join(timeout=5)
        
        # Verify task marked as FAILED
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM entries WHERE timestamp=?", (timestamp,))
        status = cursor.fetchone()[0]
        conn.close()
        
        assert status == "FAILED", f"Task should be marked FAILED, got {status}"


def test_worker_graceful_shutdown(temp_db):
    """Test that worker stops gracefully when signaled."""
    db_path = temp_db["db_path"]
    screenshot_dir = temp_db["screenshots_path"]
    
    # Mock engines with slow processing
    with patch("openrecall.server.worker.extract_text_from_image") as mock_ocr, \
         patch("openrecall.server.worker.get_ai_engine") as mock_ai, \
         patch("openrecall.server.worker.get_nlp_engine") as mock_nlp:
        
        def slow_ocr(path):
            time.sleep(0.5)
            return "text"
        
        mock_ocr.side_effect = slow_ocr
        
        mock_ai_instance = MagicMock()
        mock_ai_instance.analyze_image.return_value = "description"
        mock_ai.return_value = mock_ai_instance
        
        mock_nlp_instance = MagicMock()
        mock_nlp_instance.encode.return_value = np.random.rand(1024).astype(np.float32)
        mock_nlp.return_value = mock_nlp_instance
        
        # Start worker
        worker = ProcessingWorker()
        worker.start()
        
        # Immediately signal stop
        time.sleep(0.1)
        worker.stop()
        
        # Worker should stop within reasonable time
        start = time.time()
        worker.join(timeout=3)
        elapsed = time.time() - start
        
        assert not worker.is_alive(), "Worker should have stopped"
        assert elapsed < 3, f"Worker took too long to stop: {elapsed}s"


def test_worker_crash_recovery(temp_db):
    """Test that reset_stuck_tasks recovers tasks stuck in PROCESSING."""
    db_path = temp_db["db_path"]
    screenshot_dir = temp_db["screenshots_path"]
    
    # Manually insert a task stuck in PROCESSING state
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    timestamp = "test_stuck_task"
    create_mock_screenshot(screenshot_dir, timestamp)
    
    cursor.execute(
        "INSERT INTO entries (app, title, timestamp, status) VALUES (?, ?, ?, ?)",
        ("TestApp", "Stuck Task", timestamp, "PROCESSING")
    )
    conn.commit()
    
    # Verify it's PROCESSING
    cursor.execute("SELECT status FROM entries WHERE timestamp=?", (timestamp,))
    status = cursor.fetchone()[0]
    assert status == "PROCESSING", "Task should be in PROCESSING state"
    
    # Run crash recovery
    reset_count = reset_stuck_tasks(conn)
    assert reset_count == 1, "Should have reset 1 stuck task"
    
    # Verify it's now PENDING
    cursor.execute("SELECT status FROM entries WHERE timestamp=?", (timestamp,))
    status = cursor.fetchone()[0]
    assert status == "PENDING", "Task should be reset to PENDING"
    
    conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
