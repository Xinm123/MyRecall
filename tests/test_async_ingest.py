"""Tests for Phase 6.4.2 - Fast Ingestion (Fire-and-Forget)."""

import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from openrecall.shared.config import Settings
from openrecall.server import database
from openrecall.server.app import app


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        db_path = temp_dir / "db" / "recall.db"
        test_settings = Settings(
            base_path=temp_dir,
            debug=False,
        )
        monkeypatch.setattr("openrecall.server.database.settings", test_settings)
        monkeypatch.setattr("openrecall.server.api.settings", test_settings)
        database.create_db()
        yield test_settings


def test_fast_ingestion_endpoint(temp_db):
    """Test that /upload is fast and creates PENDING entry."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    # Create a test image
    test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    
    payload = {
        "image": test_image.flatten().tolist(),
        "shape": list(test_image.shape),
        "dtype": str(test_image.dtype),
        "timestamp": 1234567890,
        "active_app": "TestApp",
        "active_window": "Test Window",
    }
    
    # Measure response time
    start = time.perf_counter()
    response = client.post('/api/upload', json=payload)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    # Assert: Fast response (< 100ms is very generous, should be < 50ms)
    assert elapsed_ms < 100, f"Ingestion took {elapsed_ms:.1f}ms, expected < 100ms"
    
    # Assert: HTTP 202 Accepted
    assert response.status_code == 202, f"Expected 202, got {response.status_code}"
    
    # Assert: Response contains task_id
    data = response.get_json()
    assert data["status"] == "accepted"
    assert "task_id" in data
    assert data["task_id"] is not None
    
    # Assert: Database has PENDING entry
    import sqlite3
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, text, description, embedding FROM entries WHERE timestamp=?", (1234567890,))
        row = cursor.fetchone()
        
        assert row is not None, "Entry should exist in database"
        status, text, description, embedding = row
        assert status == "PENDING", f"Expected PENDING status, got {status}"
        assert text is None, "Text should be None (not processed yet)"
        assert description is None, "Description should be None (not processed yet)"
        assert embedding is None, "Embedding should be None (not processed yet)"


def test_ingestion_saves_image(temp_db):
    """Test that image file is saved to screenshots directory."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    test_image = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
    timestamp = 9999999999
    
    payload = {
        "image": test_image.flatten().tolist(),
        "shape": list(test_image.shape),
        "dtype": str(test_image.dtype),
        "timestamp": timestamp,
        "active_app": "TestApp",
        "active_window": "Test",
    }
    
    response = client.post('/api/upload', json=payload)
    assert response.status_code == 202
    
    # Check that image file was saved
    expected_path = temp_db.screenshots_path / f"{timestamp}.png"
    assert expected_path.exists(), f"Image should be saved at {expected_path}"


def test_duplicate_timestamp_rejected(temp_db):
    """Test that duplicate timestamps are rejected."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    test_image = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
    
    payload = {
        "image": test_image.flatten().tolist(),
        "shape": list(test_image.shape),
        "dtype": str(test_image.dtype),
        "timestamp": 5555555555,
        "active_app": "TestApp",
        "active_window": "Test",
    }
    
    # First upload: should succeed
    response1 = client.post('/api/upload', json=payload)
    assert response1.status_code == 202
    
    # Second upload with same timestamp: should fail
    response2 = client.post('/api/upload', json=payload)
    assert response2.status_code == 409  # Conflict
    data = response2.get_json()
    assert "duplicate" in data["message"].lower() or "failed" in data["message"].lower()


def test_response_time_measurement(temp_db):
    """Test that response includes elapsed_ms field."""
    app.config['TESTING'] = True
    client = app.test_client()
    
    test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    
    payload = {
        "image": test_image.flatten().tolist(),
        "shape": list(test_image.shape),
        "dtype": str(test_image.dtype),
        "timestamp": 7777777777,
        "active_app": "TestApp",
        "active_window": "Test",
    }
    
    response = client.post('/api/upload', json=payload)
    assert response.status_code == 202
    
    data = response.get_json()
    assert "elapsed_ms" in data
    assert isinstance(data["elapsed_ms"], (int, float))
    assert data["elapsed_ms"] > 0
    assert data["elapsed_ms"] < 100  # Should be very fast
