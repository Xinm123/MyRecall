
import pytest
import sqlite3
import time
import shutil
from unittest.mock import MagicMock, patch
from flask.testing import FlaskClient

from openrecall.server.app import app
from openrecall.server.worker import ProcessingWorker
from openrecall.server.database import SQLStore, VectorStore
from openrecall.shared.models import RecallEntry

@pytest.fixture
def init_stores(mock_settings):
    """Initialize real SQLite and LanceDB in temp dirs."""
    # Patch settings where SQLStore/VectorStore import it
    with patch("openrecall.server.database.sql.settings", mock_settings), \
         patch("openrecall.server.database.vector_store.settings", mock_settings):
        
        sql = SQLStore()
        vec = VectorStore()
        
        # Tables are created by SQLStore.__init__ and VectorStore.__init__
        if hasattr(vec, "create_table"):
            vec.create_table()
        
        yield sql, vec

@pytest.fixture
def test_client(mock_settings, mock_ai_provider, init_stores):
    """Create a Flask test client with mocked dependencies."""
    sql_store, vector_store = init_stores
    
    # We need to patch the global settings used by the app AND the global sql_store
    with patch("openrecall.server.api.settings", mock_settings), \
         patch("openrecall.server.worker.settings", mock_settings), \
         patch("openrecall.server.app.settings", mock_settings), \
         patch("openrecall.server.app.sql_store", sql_store), \
         patch("openrecall.server.api.sql_store", sql_store), \
         patch("openrecall.server.worker.get_ai_provider", return_value=mock_ai_provider), \
         patch("openrecall.server.worker.get_ocr_provider", return_value=mock_ai_provider), \
         patch("openrecall.server.worker.get_embedding_provider", return_value=mock_ai_provider):
        
        # Configure app for testing
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

def test_full_ingestion_cycle(test_client, mock_settings, init_stores):
    """
    E2E Test: Upload -> Worker Process -> DB Check
    """
    sql_store, vector_store = init_stores
    
    # 1. Create a dummy image
    img_path = mock_settings.server_data_dir / "test.png"
    img_path.write_bytes(b"fake image content")
    
    # 2. Upload via API
    with open(img_path, "rb") as f:
        response = test_client.post(
            "/api/upload",
            data={
                "file": (f, "test.png"),
                "metadata": '{"app_name": "TestApp", "window_title": "TestTitle", "timestamp": 100.0}'
            }
        )
    
    assert response.status_code == 202
    task_id = response.get_json()["task_id"]
    
    # 3. Verify PENDING state in SQLite
    conn = sqlite3.connect(mock_settings.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM entries WHERE id=?", (task_id,))
    status = cursor.fetchone()[0]
    assert status == "PENDING"
    conn.close()
    
    # 4. Trigger Worker Manually
    # We instantiate the worker and run _process_task directly to avoid threading issues in tests
    worker = ProcessingWorker()
    
    # Need to get the task object
    conn = sqlite3.connect(mock_settings.db_path)
    task = sql_store.get_next_task(conn)
    assert task.id == task_id
    
    # Mock providers are injected via the patch in test_client fixture context
    # But here we need to pass them explicitly if we call _process_task
    # Or simpler: run the loop for one iteration.
    # Let's call _process_task directly.
    
    mock_provider = MagicMock()
    mock_provider.extract_text.return_value = "Test OCR Text"
    mock_provider.analyze_image.return_value = {"caption": "Test Caption"}
    import numpy as np
    mock_provider.embed_text.return_value = np.array([0.1] * 1024, dtype=np.float32)

    # We must ensure the image exists where the worker expects it
    # API saves to settings.screenshots_path / {timestamp}.png
    # timestamp was 100.0
    expected_path = mock_settings.screenshots_path / "100.0.png"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_bytes(b"fake image")
    
    worker._process_task(
        conn, 
        task, 
        mock_provider, # AI
        mock_provider, # OCR
        mock_provider, # Embedding
        vector_store, 
        sql_store,
        ai_processing_version=0
    )
    
    # 5. Verify COMPLETED state
    cursor = conn.cursor()
    cursor.execute("SELECT status, text, description FROM entries WHERE id=?", (task_id,))
    row = cursor.fetchone()
    assert row[0] == "COMPLETED"
    assert row[1] == "Test OCR Text"
    assert row[2] == "Test Caption"
    conn.close()
    
    # 6. Verify LanceDB
    results = vector_store.search([0.1]*1024, limit=1)
    assert len(results) == 1
    assert results[0][0].content.caption == "Test Caption"

def test_queue_priority_lifo(test_client, mock_settings, init_stores):
    """
    Test LIFO logic: When queue > threshold (5 in mock), new tasks process first.
    """
    sql_store, _ = init_stores
    conn = sqlite3.connect(mock_settings.db_path)
    
    # Insert 6 tasks (Threshold is 5)
    # Tasks 1-5 (Old)
    for i in range(1, 6):
        sql_store.insert_pending_entry(int(i), "App", "Title", f"/tmp/img{i}.png")
        
    # Task 6 (Newest)
    sql_store.insert_pending_entry(6, "App", "Title", "/tmp/img6.png")
    
    # Check count
    count = sql_store.get_pending_count(conn)
    assert count == 6
    
    # Worker should pick LIFO (Newest) because 6 >= 5
    worker = ProcessingWorker()
    
    # We need to simulate the worker's selection logic
    # get_next_task(lifo_mode=True)
    task = sql_store.get_next_task(conn, lifo_mode=True)
    
    assert task.timestamp == 6 # The newest one
    
    conn.close()

def test_queue_priority_fifo(test_client, mock_settings, init_stores):
    """
    Test FIFO logic: When queue < threshold, old tasks process first.
    """
    sql_store, _ = init_stores
    conn = sqlite3.connect(mock_settings.db_path)
    
    # Insert 3 tasks (Threshold is 5)
    for i in range(1, 4):
        sql_store.insert_pending_entry(int(i), "App", "Title", f"/tmp/img{i}.png")
        
    count = sql_store.get_pending_count(conn)
    assert count == 3
    
    # Worker should pick FIFO (Oldest) because 3 < 5
    task = sql_store.get_next_task(conn, lifo_mode=False)
    
    assert task.timestamp == 1 # The oldest one
    
    conn.close()
