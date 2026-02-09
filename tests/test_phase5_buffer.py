"""Phase 5 Buffer & Consumer Tests.

Tests for offline resilience and Producer-Consumer architecture.
"""

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


class TestLocalBuffer:
    """Tests for LocalBuffer class."""

    @pytest.fixture
    def buffer_dir(self, tmp_path):
        """Create a temporary buffer directory."""
        return tmp_path / "buffer"

    @pytest.fixture
    def buffer(self, buffer_dir):
        """Create a LocalBuffer instance."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            return LocalBuffer(storage_dir=buffer_dir)

    @pytest.fixture
    def sample_image(self):
        """Create a sample PIL Image."""
        arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        return Image.fromarray(arr)

    def test_enqueue_creates_files(self, buffer, sample_image, buffer_dir):
        """Test that enqueue creates .webp and .json files."""
        metadata = {"timestamp": 1234567890, "active_app": "TestApp"}
        
        item_id = buffer.enqueue(sample_image, metadata)
        
        assert (buffer_dir / f"{item_id}.webp").exists()
        assert (buffer_dir / f"{item_id}.json").exists()
        # Temp file should not exist
        assert not (buffer_dir / f"{item_id}.json.tmp").exists()

    def test_enqueue_atomic_write(self, buffer, sample_image, buffer_dir):
        """Test that .json.tmp is renamed to .json (atomic)."""
        metadata = {"timestamp": 123}
        
        item_id = buffer.enqueue(sample_image, metadata)
        
        # Read back and verify
        with open(buffer_dir / f"{item_id}.json") as f:
            saved_meta = json.load(f)
        
        assert saved_meta["timestamp"] == 123

    def test_get_next_batch_fifo_order(self, buffer, sample_image):
        """Test that items are returned in FIFO order."""
        ids = []
        for i in range(3):
            ids.append(buffer.enqueue(sample_image, {"timestamp": i}))
            time.sleep(0.01)  # Ensure different timestamps
        
        batch = buffer.get_next_batch(limit=2)
        
        assert len(batch) == 2
        assert batch[0].id == ids[0]  # Oldest first
        assert batch[1].id == ids[1]

    def test_get_next_batch_empty(self, buffer):
        """Test empty buffer returns empty list."""
        batch = buffer.get_next_batch(limit=1)
        assert batch == []

    def test_commit_deletes_files(self, buffer, sample_image, buffer_dir):
        """Test that commit deletes both .webp and .json files."""
        item_id = buffer.enqueue(sample_image, {"timestamp": 123})
        
        buffer.commit([item_id])
        
        assert not (buffer_dir / f"{item_id}.webp").exists()
        assert not (buffer_dir / f"{item_id}.json").exists()

    def test_orphan_json_cleanup(self, buffer, sample_image, buffer_dir):
        """Test that orphan .json files (no .webp) are cleaned up."""
        item_id = buffer.enqueue(sample_image, {"timestamp": 123})
        
        # Delete just the image (simulating corruption)
        (buffer_dir / f"{item_id}.webp").unlink()
        
        # get_next_batch should clean up the orphan
        batch = buffer.get_next_batch(limit=1)
        
        assert batch == []
        assert not (buffer_dir / f"{item_id}.json").exists()

    def test_count(self, buffer, sample_image):
        """Test buffer count."""
        assert buffer.count() == 0
        
        buffer.enqueue(sample_image, {"timestamp": 1})
        buffer.enqueue(sample_image, {"timestamp": 2})
        
        assert buffer.count() == 2

    def test_datetime_serialization(self, buffer, sample_image, buffer_dir):
        """Test that datetime objects are serialized to ISO format."""
        from datetime import datetime
        
        now = datetime.now()
        metadata = {"timestamp": 123, "created_at": now}
        
        item_id = buffer.enqueue(sample_image, metadata)
        
        with open(buffer_dir / f"{item_id}.json") as f:
            saved_meta = json.load(f)
        
        assert saved_meta["created_at"] == now.isoformat()

    def test_path_serialization(self, buffer, sample_image, buffer_dir):
        """Test that Path objects are serialized to strings."""
        metadata = {"timestamp": 123, "path": Path("/some/path")}
        
        item_id = buffer.enqueue(sample_image, metadata)
        
        with open(buffer_dir / f"{item_id}.json") as f:
            saved_meta = json.load(f)
        
        assert saved_meta["path"] == "/some/path"


class TestUploaderConsumer:
    """Tests for UploaderConsumer class."""

    @pytest.fixture
    def buffer_dir(self, tmp_path):
        return tmp_path / "buffer"

    @pytest.fixture
    def mock_uploader(self):
        """Create a mock HTTPUploader."""
        uploader = MagicMock()
        uploader.upload_screenshot.return_value = True
        return uploader

    def test_consumer_stops_on_signal(self, buffer_dir, mock_uploader):
        """Test that consumer stops when stop() is called."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer
            
            buffer = LocalBuffer(storage_dir=buffer_dir)
            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            
            consumer.start()
            time.sleep(0.1)
            
            consumer.stop()
            consumer.join(timeout=2.0)
            
            assert not consumer.is_alive()

    def test_consumer_uploads_and_commits(self, buffer_dir, mock_uploader):
        """Test that consumer uploads items and deletes them."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer
            
            buffer = LocalBuffer(storage_dir=buffer_dir)
            
            # Add item to buffer
            arr = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
            image = Image.fromarray(arr)
            item_id = buffer.enqueue(image, {"timestamp": 123, "active_app": "Test", "active_window": "Win"})
            
            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()
            
            # Wait for processing
            time.sleep(0.5)
            
            consumer.stop()
            consumer.join(timeout=2.0)
            
            # Verify upload was called
            mock_uploader.upload_screenshot.assert_called()
            
            # Verify item was deleted
            assert buffer.count() == 0

    def test_consumer_uploads_video_chunk_and_commits(self, buffer_dir, mock_uploader):
        """Video chunk items should be dispatched to upload_video_chunk."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer

            buffer = LocalBuffer(storage_dir=buffer_dir)

            src_chunk = buffer_dir.parent / "chunk_test.mp4"
            src_chunk.write_bytes(b"not-a-real-mp4")
            metadata = {
                "type": "video_chunk",
                "timestamp": 123,
                "checksum": "abc123",
                "monitor_id": 1,
            }
            buffer.enqueue_file(str(src_chunk), metadata)

            mock_uploader.upload_video_chunk.return_value = True

            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()

            time.sleep(0.5)

            consumer.stop()
            consumer.join(timeout=2.0)

            mock_uploader.upload_video_chunk.assert_called_once()
            mock_uploader.upload_screenshot.assert_not_called()
            assert buffer.count() == 0

    def test_consumer_logs_item_type_and_target_branch(self, buffer_dir, mock_uploader, caplog):
        """Consumer logs item_type and uploader branch for troubleshooting."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer

            buffer = LocalBuffer(storage_dir=buffer_dir)
            src_chunk = buffer_dir.parent / "chunk_log_test.mp4"
            src_chunk.write_bytes(b"not-a-real-mp4")
            buffer.enqueue_file(str(src_chunk), {"type": "video_chunk", "timestamp": 456})

            mock_uploader.upload_video_chunk.return_value = True
            caplog.set_level("INFO", logger="openrecall.client.consumer")

            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()
            time.sleep(0.5)
            consumer.stop()
            consumer.join(timeout=2.0)

            messages = [r.message for r in caplog.records]
            assert any("Dispatch buffered item" in m and "item_type=video_chunk" in m and "target=upload_video_chunk" in m for m in messages)

    def test_consumer_logs_video_upload_details(self, buffer_dir, mock_uploader, caplog):
        """Video uploads should log filename/size/monitor details."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer

            buffer = LocalBuffer(storage_dir=buffer_dir)
            src_chunk = buffer_dir.parent / "chunk_detail_test.mp4"
            src_chunk.write_bytes(b"video-data-for-log-test")
            buffer.enqueue_file(
                str(src_chunk),
                {
                    "type": "video_chunk",
                    "timestamp": 456,
                    "monitor_id": "1",
                    "chunk_filename": "chunk_detail_test.mp4",
                },
            )

            mock_uploader.upload_video_chunk.return_value = True
            caplog.set_level("INFO", logger="openrecall.client.consumer")

            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()
            time.sleep(0.5)
            consumer.stop()
            consumer.join(timeout=2.0)

            messages = [r.message for r in caplog.records]
            assert any(
                "Uploading video chunk" in m
                and "chunk_detail_test.mp4" in m
                and "monitor_id=1" in m
                for m in messages
            )
            assert any(
                "Uploaded video chunk" in m
                and "chunk_detail_test.mp4" in m
                and "remaining=" in m
                for m in messages
            )

    def test_consumer_retries_on_failure(self, buffer_dir):
        """Test item preserved on failure (not deleted)."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer
            
            mock_uploader = MagicMock()
            mock_uploader.upload_screenshot.return_value = False  # Always fail
            
            buffer = LocalBuffer(storage_dir=buffer_dir)
            
            arr = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
            image = Image.fromarray(arr)
            buffer.enqueue(image, {"timestamp": 123, "active_app": "Test", "active_window": "Win"})
            
            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()
            
            time.sleep(0.3)
            
            consumer.stop()
            consumer.join(timeout=2.0)
            
            # Item should still be in buffer (not deleted on failure)
            assert buffer.count() == 1

    def test_consumer_interruptible_backoff(self, buffer_dir):
        """Test that consumer can be stopped during backoff."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(buffer_dir.parent)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer
            
            mock_uploader = MagicMock()
            mock_uploader.upload_screenshot.return_value = False  # Trigger backoff
            
            buffer = LocalBuffer(storage_dir=buffer_dir)
            
            arr = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
            image = Image.fromarray(arr)
            buffer.enqueue(image, {"timestamp": 123, "active_app": "Test", "active_window": "Win"})
            
            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()
            
            time.sleep(0.2)  # Let it fail and start backoff
            
            start = time.time()
            consumer.stop()
            consumer.join(timeout=2.0)
            elapsed = time.time() - start
            
            # Should exit quickly despite potential 60s backoff
            assert elapsed < 1.0
            assert not consumer.is_alive()


class TestProducerConsumerIntegration:
    """Integration tests for Producer-Consumer architecture."""

    def test_buffer_persists_across_restart(self, tmp_path):
        """Test that buffer files survive process restart."""
        buffer_dir = tmp_path / "buffer"
        
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(tmp_path)}):
            from openrecall.client.buffer import LocalBuffer
            
            # First "process": create buffer and add items
            buffer1 = LocalBuffer(storage_dir=buffer_dir)
            arr = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
            image = Image.fromarray(arr)
            buffer1.enqueue(image, {"timestamp": 1})
            buffer1.enqueue(image, {"timestamp": 2})
            
            # Simulate restart: create new buffer instance
            buffer2 = LocalBuffer(storage_dir=buffer_dir)
            
            # Should see the old items
            assert buffer2.count() == 2
            batch = buffer2.get_next_batch(limit=2)
            assert len(batch) == 2

    def test_no_data_loss_on_network_failure(self, tmp_path):
        """Test that items remain in buffer when upload fails."""
        buffer_dir = tmp_path / "buffer"
        
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(tmp_path)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer
            
            mock_uploader = MagicMock()
            mock_uploader.upload_screenshot.return_value = False
            
            buffer = LocalBuffer(storage_dir=buffer_dir)
            
            # Add multiple items
            arr = np.random.randint(0, 255, (10, 10, 3), dtype=np.uint8)
            image = Image.fromarray(arr)
            for i in range(3):
                buffer.enqueue(image, {"timestamp": i, "active_app": "Test", "active_window": "Win"})
            
            initial_count = buffer.count()
            
            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            consumer.start()
            time.sleep(0.3)
            consumer.stop()
            consumer.join(timeout=2.0)
            
            # All items should still be in buffer
            assert buffer.count() == initial_count


class TestScreenRecorder:
    """Tests for ScreenRecorder class."""

    def test_recorder_stop_graceful(self, tmp_path):
        """Test that recorder stops gracefully."""
        with patch.dict("os.environ", {"OPENRECALL_DATA_DIR": str(tmp_path)}):
            from openrecall.client.buffer import LocalBuffer
            from openrecall.client.consumer import UploaderConsumer
            from openrecall.client.recorder import ScreenRecorder
            
            mock_uploader = MagicMock()
            mock_uploader.upload_screenshot.return_value = True
            
            buffer = LocalBuffer(storage_dir=tmp_path / "buffer")
            consumer = UploaderConsumer(buffer=buffer, uploader=mock_uploader)
            recorder = ScreenRecorder(buffer=buffer, consumer=consumer)
            
            # Start consumer only (not full capture loop)
            recorder.start()
            time.sleep(0.1)
            
            recorder.stop()
            
            assert not recorder.consumer.is_alive()
