"""Tests for accessibility-canonical ingest path.

Phase 5 of Chat MVP implementation.

These tests verify the server-side ingest path for accessibility-canonical frames.
SSOT: docs/v3/chat/mvp.md
"""

import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


def generate_uuid7() -> str:
    """Generate a UUID v7 for testing.

    UUID v7 is time-sortable and has a specific format.
    For testing purposes, we use uuid.uuid4() but format it correctly.
    The ingest validation checks for version 7, so we need to be careful.
    """
    # Generate a UUID v7 format: use timestamp-based approach
    # For testing, just use uuid4 - the validation may be lenient for testing
    # or we can generate a proper v7 format
    import time
    timestamp_ms = int(time.time() * 1000)
    # Create a UUID v7 from timestamp
    # Format: time_low (32 bits) | time_mid (16 bits) | time_hi_and_version (16 bits)
    # | clock_seq_hi_and_reserved (8 bits) | clock_seq_low (8 bits) | node (48 bits)
    time_low = timestamp_ms & 0xFFFFFFFF
    time_mid = (timestamp_ms >> 32) & 0xFFFF
    time_hi_and_version = ((timestamp_ms >> 48) & 0x0FFF) | 0x7000
    clock_seq = (uuid.uuid4().int >> 64) & 0x3FFF | 0x8000
    node = uuid.uuid4().int & 0xFFFFFFFFFFFF
    return uuid.UUID(fields=(time_low, time_mid, time_hi_and_version,
                             clock_seq >> 8, clock_seq & 0xFF, node)).hex


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database with v3 schema."""
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db: Path) -> FramesStore:
    """Create a FramesStore with temporary database."""
    return FramesStore(db_path=temp_db)


@pytest.fixture
def accessibility_payload():
    """Sample accessibility payload for testing."""
    return {
        "text_content": "Hello World\nFoo Bar",
        "tree_json": json.dumps([
            {"role": "AXStaticText", "text": "Hello World", "depth": 0, "bounds": None},
            {"role": "AXStaticText", "text": "Foo Bar", "depth": 1, "bounds": None},
        ]),
        "node_count": 2,
        "truncated": False,
        "truncation_reason": None,
        "max_depth_reached": 2,
        "duration_ms": 50,
    }


class TestAccessibilityCanonicalIngest:
    """Tests for accessibility-canonical ingest path."""

    def test_ingest_completes_accessibility_canonical_frame(
        self, store: FramesStore, tmp_path: Path, accessibility_payload
    ):
        """Accessibility-canonical payload should synchronously complete the frame."""
        # Create test JPEG
        jpeg_path = tmp_path / "test.jpg"
        jpeg_path.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        )

        metadata = {
            "timestamp": "2026-03-20T10:00:00Z",
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "app_name": "Safari",
            "window_name": "Doc",
            "focused": True,
            "text": "Hello World\nFoo Bar",
            "text_source": "accessibility",
            "browser_url": "https://example.com",
            "content_hash": 12345,
            "simhash": 67890,
            "accessibility": accessibility_payload,
        }

        # Claim the frame
        frame_id, is_new = store.claim_frame(
            capture_id="test-capture-1",
            metadata=metadata,
        )

        assert is_new is True
        assert frame_id is not None

        # Simulate completing with accessibility data
        tree_nodes = json.loads(accessibility_payload["tree_json"])
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text=metadata["text"],
            browser_url=metadata.get("browser_url"),
            content_hash=metadata.get("content_hash"),
            simhash=metadata.get("simhash"),
            accessibility_tree_json=accessibility_payload["tree_json"],
            accessibility_text_content=accessibility_payload["text_content"],
            accessibility_node_count=accessibility_payload["node_count"],
            accessibility_truncated=accessibility_payload["truncated"],
            elements=tree_nodes,
        )

        # Verify frame is completed
        frame = store.get_frame_by_capture_id("test-capture-1")
        assert frame is not None
        # Check status via direct DB query since Frame dataclass may not have all fields
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, text_source, text FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "completed"
            assert row["text_source"] == "accessibility"
            assert row["text"] == "Hello World\nFoo Bar"

    def test_ingest_degrades_bad_accessibility_payload_to_pending(
        self, store: FramesStore, tmp_path: Path
    ):
        """Malformed accessibility payload should degrade to OCR-pending, not fail ingest."""
        # Invalid tree_json (not valid JSON)
        metadata = {
            "timestamp": "2026-03-20T10:00:00Z",
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "app_name": "Safari",
            "text": "Hello",
            "text_source": "accessibility",
            "accessibility": {
                "text_content": "Hello",
                "tree_json": "not valid json {{{",
                "node_count": 1,
                "truncated": False,
            },
        }

        # Claim the frame - this should still work
        frame_id, is_new = store.claim_frame(
            capture_id="test-capture-2",
            metadata=metadata,
        )

        assert is_new is True

        # Frame should be in pending status since accessibility couldn't be completed
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, text_source FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "pending"
            assert row["text_source"] is None

    def test_complete_accessibility_frame_writes_all_tables(
        self, store: FramesStore, accessibility_payload
    ):
        """complete_accessibility_frame should write frames, accessibility, elements."""
        # First create a claimed frame
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-3",
            metadata={
                "timestamp": "2026-03-20T10:00:00Z",
                "app_name": "Safari",
                "window_name": "Doc",
                "browser_url": None,
                "focused": True,
                "device_name": "monitor_1",
                "capture_trigger": "click",
            },
        )

        # Complete it with accessibility
        tree_nodes = json.loads(accessibility_payload["tree_json"])
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="Hello World",
            browser_url="https://example.com",
            content_hash=12345,
            simhash=67890,
            accessibility_tree_json=accessibility_payload["tree_json"],
            accessibility_text_content="Hello World",
            accessibility_node_count=2,
            accessibility_truncated=False,
            elements=tree_nodes,
        )

        # Verify frame
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            frame_row = conn.execute(
                "SELECT * FROM frames WHERE id = ?", (frame_id,)
            ).fetchone()
            assert frame_row["status"] == "completed"
            assert frame_row["text_source"] == "accessibility"

            # Verify accessibility row
            acc_rows = conn.execute(
                "SELECT * FROM accessibility WHERE frame_id = ?", (frame_id,)
            ).fetchall()
            assert len(acc_rows) == 1
            assert acc_rows[0]["text_content"] == "Hello World"

            # Verify elements rows
            elem_rows = conn.execute(
                "SELECT * FROM elements WHERE frame_id = ? ORDER BY sort_order",
                (frame_id,),
            ).fetchall()
            assert len(elem_rows) == 2

    def test_ingest_elements_have_correct_parent_id_and_sort_order(
        self, store: FramesStore, tmp_path: Path
    ):
        """Elements should have parent_id and sort_order derived from depth-first ordering."""
        # Tree: root -> child1 -> grandchild, child2
        tree_json = json.dumps([
            {"role": "AXGroup", "text": "", "depth": 0},
            {"role": "AXStaticText", "text": "Child 1", "depth": 1},
            {"role": "AXStaticText", "text": "Grandchild", "depth": 2},
            {"role": "AXStaticText", "text": "Child 2", "depth": 1},
        ])

        metadata = {
            "timestamp": "2026-03-20T10:00:00Z",
            "app_name": "Safari",
            "text": "Child 1 Grandchild Child 2",
            "text_source": "accessibility",
            "accessibility": {
                "text_content": "Child 1 Grandchild Child 2",
                "tree_json": tree_json,
                "node_count": 4,
            },
        }

        frame_id, _ = store.claim_frame(
            capture_id="test-capture-4",
            metadata=metadata,
        )

        tree_nodes = json.loads(tree_json)
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="Child 1 Grandchild Child 2",
            browser_url=None,
            content_hash=None,
            simhash=None,
            accessibility_tree_json=tree_json,
            accessibility_text_content="Child 1 Grandchild Child 2",
            accessibility_node_count=4,
            accessibility_truncated=False,
            elements=tree_nodes,
        )

        # Verify elements have correct parent_id and sort_order
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            elem_rows = conn.execute(
                "SELECT id, role, text, depth, parent_id, sort_order FROM elements WHERE frame_id = ? ORDER BY sort_order",
                (frame_id,),
            ).fetchall()

            assert len(elem_rows) == 4

            # Element 0: root (depth 0, no parent)
            assert elem_rows[0]["role"] == "AXGroup"
            assert elem_rows[0]["depth"] == 0
            assert elem_rows[0]["parent_id"] is None
            assert elem_rows[0]["sort_order"] == 0

            # Element 1: Child 1 (depth 1, parent is root)
            assert elem_rows[1]["text"] == "Child 1"
            assert elem_rows[1]["depth"] == 1
            assert elem_rows[1]["parent_id"] == elem_rows[0]["id"]
            assert elem_rows[1]["sort_order"] == 1

            # Element 2: Grandchild (depth 2, parent is Child 1)
            assert elem_rows[2]["text"] == "Grandchild"
            assert elem_rows[2]["depth"] == 2
            assert elem_rows[2]["parent_id"] == elem_rows[1]["id"]
            assert elem_rows[2]["sort_order"] == 2

            # Element 3: Child 2 (depth 1, parent is root)
            assert elem_rows[3]["text"] == "Child 2"
            assert elem_rows[3]["depth"] == 1
            assert elem_rows[3]["parent_id"] == elem_rows[0]["id"]
            assert elem_rows[3]["sort_order"] == 3


class TestCompleteAccessibilityFrame:
    """Tests for complete_accessibility_frame method."""

    def test_complete_accessibility_frame_is_idempotent(
        self, store: FramesStore, accessibility_payload
    ):
        """Calling complete_accessibility_frame twice should not fail."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-idempotent",
            metadata={
                "timestamp": "2026-03-20T10:00:00Z",
                "app_name": "Safari",
            },
        )

        tree_nodes = json.loads(accessibility_payload["tree_json"])

        # First call should succeed
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="Hello World",
            browser_url="https://example.com",
            content_hash=12345,
            simhash=67890,
            accessibility_tree_json=accessibility_payload["tree_json"],
            accessibility_text_content="Hello World",
            accessibility_node_count=2,
            accessibility_truncated=False,
            elements=tree_nodes,
        )

        # Second call should also succeed (update, not insert)
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="Hello World Updated",
            browser_url="https://example.com/updated",
            content_hash=99999,
            simhash=11111,
            accessibility_tree_json=accessibility_payload["tree_json"],
            accessibility_text_content="Hello World Updated",
            accessibility_node_count=2,
            accessibility_truncated=False,
            elements=tree_nodes,
        )

        # Verify final state
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            frame = conn.execute(
                "SELECT text, browser_url FROM frames WHERE id = ?", (frame_id,)
            ).fetchone()
            assert frame["text"] == "Hello World Updated"
            assert frame["browser_url"] == "https://example.com/updated"

    def test_complete_accessibility_frame_with_empty_elements(
        self, store: FramesStore
    ):
        """complete_accessibility_frame should handle empty elements list."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-empty",
            metadata={
                "timestamp": "2026-03-20T10:00:00Z",
                "app_name": "Safari",
            },
        )

        # Should not raise
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="",
            browser_url=None,
            content_hash=None,
            simhash=None,
            accessibility_tree_json="[]",
            accessibility_text_content="",
            accessibility_node_count=0,
            accessibility_truncated=False,
            elements=[],
        )

        # Verify frame is completed
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            frame = conn.execute(
                "SELECT status FROM frames WHERE id = ?", (frame_id,)
            ).fetchone()
            assert frame["status"] == "completed"

    def test_complete_accessibility_frame_with_bounds(
        self, store: FramesStore
    ):
        """complete_accessibility_frame should correctly store element bounds."""
        tree_json = json.dumps([
            {
                "role": "AXButton",
                "text": "Click Me",
                "depth": 0,
                "bounds": {"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.4},
            },
        ])

        frame_id, _ = store.claim_frame(
            capture_id="test-capture-bounds",
            metadata={
                "timestamp": "2026-03-20T10:00:00Z",
                "app_name": "Safari",
            },
        )

        tree_nodes = json.loads(tree_json)
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="Click Me",
            browser_url=None,
            content_hash=None,
            simhash=None,
            accessibility_tree_json=tree_json,
            accessibility_text_content="Click Me",
            accessibility_node_count=1,
            accessibility_truncated=False,
            elements=tree_nodes,
        )

        # Verify bounds were stored correctly
        with sqlite3.connect(str(store.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            elem = conn.execute(
                "SELECT left_bound, top_bound, width_bound, height_bound FROM elements WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()

            assert elem["left_bound"] == 0.1
            assert elem["top_bound"] == 0.2
            assert elem["width_bound"] == 0.3
            assert elem["height_bound"] == 0.4


class TestHttpAccessibilityIngest:
    """HTTP integration tests for accessibility-canonical ingest path."""

    @pytest.fixture
    def test_client(self, tmp_path: Path, monkeypatch):
        """Create a Flask test client with temporary data directory."""
        import importlib

        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path / "server"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)

        from openrecall.server.api_v1 import v1_bp, _get_frames_store

        # Reset store singleton
        import openrecall.server.api_v1 as api_module
        api_module._frames_store = None

        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(v1_bp)

        return app.test_client(), tmp_path

    def test_http_ingest_accessibility_canonical(
        self, test_client, accessibility_payload
    ):
        """HTTP ingest with accessibility-canonical payload should return completed status."""
        client, tmp_path = test_client

        capture_id = generate_uuid7()
        metadata = {
            "timestamp": "2026-03-20T10:00:00Z",
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "app_name": "Safari",
            "window_name": "Doc",
            "focused": True,
            "text": "Hello World\nFoo Bar",
            "text_source": "accessibility",
            "browser_url": "https://example.com",
            "accessibility": accessibility_payload,
        }

        # Create a minimal JPEG file
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

        response = client.post(
            "/v1/ingest",
            data={
                "capture_id": capture_id,
                "metadata": json.dumps(metadata),
                "file": (io.BytesIO(jpeg_bytes), "test.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body["status"] == "completed"
        assert body["capture_id"] == capture_id

    def test_http_ingest_degrades_to_pending_on_bad_json(
        self, test_client
    ):
        """HTTP ingest with invalid accessibility JSON should degrade to pending."""
        client, tmp_path = test_client

        capture_id = generate_uuid7()
        metadata = {
            "timestamp": "2026-03-20T10:00:00Z",
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "app_name": "Safari",
            "text": "Hello",
            "text_source": "accessibility",
            "accessibility": {
                "text_content": "Hello",
                "tree_json": "not valid json {{{",
                "node_count": 1,
            },
        }

        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

        response = client.post(
            "/v1/ingest",
            data={
                "capture_id": capture_id,
                "metadata": json.dumps(metadata),
                "file": (io.BytesIO(jpeg_bytes), "test.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        # Should succeed but degrade to pending
        assert response.status_code == 201
        body = response.get_json()
        assert body["status"] == "queued"  # Degraded to OCR-pending

    def test_http_ingest_normal_without_accessibility(
        self, test_client
    ):
        """HTTP ingest without accessibility should return queued status."""
        client, tmp_path = test_client

        capture_id = generate_uuid7()
        metadata = {
            "timestamp": "2026-03-20T10:00:00Z",
            "capture_trigger": "click",
            "device_name": "monitor_1",
            "app_name": "Safari",
        }

        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

        response = client.post(
            "/v1/ingest",
            data={
                "capture_id": capture_id,
                "metadata": json.dumps(metadata),
                "file": (io.BytesIO(jpeg_bytes), "test.jpg", "image/jpeg"),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body["status"] == "queued"
