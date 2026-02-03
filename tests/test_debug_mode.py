"""Test debug mode features."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from openrecall.shared.config import Settings
from openrecall.server import database
from openrecall.server.app import app


@pytest.fixture
def temp_db_debug(monkeypatch):
    """Create a temporary test database with debug mode ON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        test_settings = Settings(
            base_path=temp_dir,
            debug=True,  # Enable debug mode
        )
        monkeypatch.setattr("openrecall.server.database.settings", test_settings)
        monkeypatch.setattr("openrecall.server.api.settings", test_settings)
        database.create_db()
        yield test_settings


def test_upload_response_includes_debug_info(temp_db_debug):
    """Test that upload response includes debug info when debug=True."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    
    payload = {
        "image": test_image.flatten().tolist(),
        "shape": list(test_image.shape),
        "dtype": str(test_image.dtype),
        "timestamp": 1111111111,
        "active_app": "TestApp",
        "active_window": "Test Window",
    }
    
    response = client.post('/api/upload', json=payload)
    assert response.status_code == 202
    
    data = response.get_json()
    assert "debug" in data, "Debug info should be included in response"
    assert "queue_size" in data["debug"]
    assert "processing_mode" in data["debug"]
    assert data["debug"]["queue_size"] >= 1  # At least the one we just added
    assert data["debug"]["processing_mode"] in ["FIFO", "LIFO"]


def test_queue_status_endpoint(temp_db_debug):
    """Test /api/queue/status endpoint."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    # Insert some test entries
    import sqlite3
    with sqlite3.connect(str(temp_db_debug.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1, 'A', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (2, 'B', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (3, 'C', 'T', 'PROCESSING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (4, 'D', 'T', 'COMPLETED')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (5, 'E', 'T', 'FAILED')")
        conn.commit()
    
    response = client.get('/api/queue/status')
    assert response.status_code == 200
    
    data = response.get_json()
    assert "queue" in data
    assert data["queue"]["pending"] == 2
    assert data["queue"]["processing"] == 1
    assert data["queue"]["completed"] == 1
    assert data["queue"]["failed"] == 1
    
    assert "config" in data
    assert "lifo_threshold" in data["config"]
    assert "current_mode" in data["config"]
    
    assert "system" in data
    assert data["system"]["debug"] is True


def test_debug_mode_disabled(monkeypatch):
    """Test that debug info is NOT included when debug=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        test_settings = Settings(
            base_path=temp_dir,
            debug=False,  # Disable debug mode
        )
        monkeypatch.setattr("openrecall.server.database.settings", test_settings)
        monkeypatch.setattr("openrecall.server.api.settings", test_settings)
        database.create_db()
        
        app.config['TESTING'] = True
        client = app.test_client()
        
        test_image = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
        
        payload = {
            "image": test_image.flatten().tolist(),
            "shape": list(test_image.shape),
            "dtype": str(test_image.dtype),
            "timestamp": 2222222222,
            "active_app": "TestApp",
            "active_window": "Test",
        }
        
        response = client.post('/api/upload', json=payload)
        assert response.status_code == 202
        
        data = response.get_json()
        assert "debug" not in data, "Debug info should NOT be included when debug=False"
