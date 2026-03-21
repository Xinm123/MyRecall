"""Tests for dual-hash (simhash + phash) storage in the frames table."""

import tempfile
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore


@pytest.fixture
def temp_db():
    """Create a temporary database with the frames table schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = FramesStore(db_path=db_path)

        # Create the frames table with both simhash and phash columns
        with store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capture_id TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    app_name TEXT,
                    window_name TEXT,
                    browser_url TEXT,
                    focused INTEGER,
                    device_name TEXT,
                    capture_trigger TEXT,
                    event_ts TEXT,
                    snapshot_path TEXT,
                    image_size_bytes INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_known_app TEXT,
                    last_known_window TEXT,
                    simhash INTEGER DEFAULT NULL,
                    phash INTEGER DEFAULT NULL
                )
            """)
            conn.commit()

        yield store


class TestExtractPhashFromMetadata:
    """Tests for _extract_metadata_fields extracting phash."""

    def test_extract_phash_from_metadata(self, temp_db):
        """Verify phash is correctly extracted from metadata."""
        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "phash": 12345678901234567890,
        }

        result = temp_db._extract_metadata_fields(metadata)
        # phash is the last element in the tuple
        phash = result[-1]
        assert phash == 12345678901234567890

    def test_extract_phash_none_when_missing(self, temp_db):
        """Verify phash is None when not provided in metadata."""
        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
        }

        result = temp_db._extract_metadata_fields(metadata)
        phash = result[-1]
        assert phash is None

    def test_extract_simhash_and_phash_independently(self, temp_db):
        """Verify simhash and phash are extracted independently."""
        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "simhash": 1111111111111111111,
            "phash": 2222222222222222222,
        }

        result = temp_db._extract_metadata_fields(metadata)
        simhash = result[-2]  # Second to last
        phash = result[-1]    # Last

        assert simhash == 1111111111111111111
        assert phash == 2222222222222222222


class TestClaimFrameStoresPhash:
    """Tests for claim_frame storing phash."""

    def test_claim_frame_stores_phash(self, temp_db):
        """Verify phash is stored to database via claim_frame."""
        # Use a value less than 2^63-1 so no conversion needed
        phash_value = 9223372036854775807  # 2^63 - 1

        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "phash": phash_value,
        }

        frame_id, is_new = temp_db.claim_frame("test-capture-1", metadata)

        assert is_new is True
        assert frame_id is not None

        # Verify phash was stored
        with temp_db._connect() as conn:
            row = conn.execute(
                "SELECT phash FROM frames WHERE capture_id = ?",
                ("test-capture-1",)
            ).fetchone()

            assert row is not None
            # Value < 2^63, so no conversion needed
            assert row["phash"] == phash_value

    def test_claim_frame_phash_nullable(self, temp_db):
        """Verify phash is nullable (None stored as NULL)."""
        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            # No phash provided
        }

        frame_id, is_new = temp_db.claim_frame("test-capture-2", metadata)

        assert is_new is True

        # Verify phash is NULL in database
        with temp_db._connect() as conn:
            row = conn.execute(
                "SELECT phash FROM frames WHERE capture_id = ?",
                ("test-capture-2",)
            ).fetchone()

            assert row is not None
            assert row["phash"] is None

    def test_claim_frame_phash_signed_conversion(self, temp_db):
        """Verify unsigned phash > 2^63-1 is converted to signed."""
        # Value > 2^63-1 should be converted to signed
        unsigned_phash = 9223372036854775808  # 2^63
        expected_signed = -9223372036854775808  # After conversion

        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "phash": unsigned_phash,
        }

        temp_db.claim_frame("test-capture-3", metadata)

        with temp_db._connect() as conn:
            row = conn.execute(
                "SELECT phash FROM frames WHERE capture_id = ?",
                ("test-capture-3",)
            ).fetchone()

            assert row is not None
            assert row["phash"] == expected_signed

    def test_simhash_and_phash_stored_independently(self, temp_db):
        """Verify simhash and phash are stored independently."""
        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "simhash": 1111111111111111111,
            "phash": 2222222222222222222,
        }

        frame_id, is_new = temp_db.claim_frame("test-capture-4", metadata)

        assert is_new is True

        with temp_db._connect() as conn:
            row = conn.execute(
                "SELECT simhash, phash FROM frames WHERE capture_id = ?",
                ("test-capture-4",)
            ).fetchone()

            assert row is not None
            assert row["simhash"] == 1111111111111111111
            assert row["phash"] == 2222222222222222222

    def test_simhash_signed_phash_unsigned_extreme(self, temp_db):
        """Test with simhash needing conversion and phash not."""
        # simhash needs conversion (> 2^63-1)
        unsigned_simhash = 18446744073709551615  # 2^64 - 1
        expected_signed_simhash = -1  # After conversion

        # phash doesn't need conversion (< 2^63)
        phash_value = 9223372036854775807  # 2^63 - 1

        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "simhash": unsigned_simhash,
            "phash": phash_value,
        }

        temp_db.claim_frame("test-capture-5", metadata)

        with temp_db._connect() as conn:
            row = conn.execute(
                "SELECT simhash, phash FROM frames WHERE capture_id = ?",
                ("test-capture-5",)
            ).fetchone()

            assert row is not None
            assert row["simhash"] == expected_signed_simhash
            assert row["phash"] == phash_value

    def test_both_hashes_need_conversion(self, temp_db):
        """Test both simhash and phash needing signed conversion."""
        unsigned_value = 18446744073709551615  # 2^64 - 1
        expected_signed = -1  # After conversion

        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "simhash": unsigned_value,
            "phash": unsigned_value,
        }

        temp_db.claim_frame("test-capture-6", metadata)

        with temp_db._connect() as conn:
            row = conn.execute(
                "SELECT simhash, phash FROM frames WHERE capture_id = ?",
                ("test-capture-6",)
            ).fetchone()

            assert row is not None
            assert row["simhash"] == expected_signed
            assert row["phash"] == expected_signed


class TestClaimFrameIdempotency:
    """Tests for claim_frame idempotency with phash."""

    def test_claim_frame_idempotent_with_phash(self, temp_db):
        """Verify claim_frame is idempotent when phash is provided."""
        metadata = {
            "timestamp": "2026-03-21T12:00:00Z",
            "phash": 12345678901234567890,
        }

        # First claim
        frame_id_1, is_new_1 = temp_db.claim_frame("test-capture-7", metadata)

        # Second claim with same capture_id
        frame_id_2, is_new_2 = temp_db.claim_frame("test-capture-7", metadata)

        assert is_new_1 is True
        assert is_new_2 is False
        assert frame_id_1 == frame_id_2
