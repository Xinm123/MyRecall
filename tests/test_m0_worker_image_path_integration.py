"""Unit tests for M0 worker image_relpath usage (Task 10)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


class MockLock:
    """Context manager mock for runtime_settings._lock."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestWorkerImageRelpath:
    """Tests for worker using image_relpath instead of timestamp-derived path."""

    def test_worker_uses_image_relpath_to_locate_file(self, tmp_path: Path) -> None:
        """Worker reads image from image_relpath when available."""
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        device_subdir = screenshots_dir / "test-device"
        device_subdir.mkdir()
        test_image_path = device_subdir / "1234567890123_abcd1234.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(test_image_path)

        from openrecall.shared.models import RecallEntry
        from openrecall.server.worker import ProcessingWorker

        task = RecallEntry(
            id=1,
            timestamp=1234567890,
            app="TestApp",
            title="Test Window",
            status="PENDING",
            device_id="test-device",
            client_ts=1234567890123,
            image_relpath="test-device/1234567890123_abcd1234.png",
        )

        captured_image_path: list[str] = []

        def mock_ocr_extract(image_path: str) -> str:
            captured_image_path.append(image_path)
            return "Mock OCR text"

        mock_ocr_provider = MagicMock()
        mock_ocr_provider.extract_text = mock_ocr_extract

        mock_ai_provider = MagicMock()
        mock_ai_provider.analyze_image.return_value = {
            "caption": "test caption",
            "scene": "test scene",
            "action": "test action",
        }

        mock_embedding_provider = MagicMock()
        mock_embedding_provider.embed_text.return_value = np.zeros(
            1024, dtype=np.float32
        )

        mock_vector_store = MagicMock()
        mock_sql_store = MagicMock()
        mock_sql_store.mark_task_completed.return_value = True

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))

        with (
            patch("openrecall.server.worker.runtime_settings") as mock_runtime,
            patch("openrecall.server.worker.settings") as mock_settings,
        ):
            mock_runtime.ai_processing_enabled = True
            mock_runtime.ai_processing_version = 1
            mock_runtime._lock = MockLock()

            mock_settings.screenshots_path = screenshots_dir
            mock_settings.debug = False
            mock_settings.embedding_dim = 1024
            mock_settings.fusion_log_enabled = False

            worker = ProcessingWorker()
            worker._process_task(
                conn,
                task,
                mock_ai_provider,
                mock_ocr_provider,
                mock_embedding_provider,
                mock_vector_store,
                mock_sql_store,
                ai_processing_version=1,
            )

        conn.close()

        assert len(captured_image_path) == 1
        assert captured_image_path[0] == str(test_image_path)

    def test_worker_falls_back_to_timestamp_path_when_image_relpath_missing(
        self, tmp_path: Path
    ) -> None:
        """Worker uses timestamp-derived path when image_relpath is None."""
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        test_image_path = screenshots_dir / "1234567890.png"
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(test_image_path)

        from openrecall.shared.models import RecallEntry
        from openrecall.server.worker import ProcessingWorker

        task = RecallEntry(
            id=2,
            timestamp=1234567890,
            app="TestApp",
            title="Test Window",
            status="PENDING",
            image_relpath=None,
        )

        captured_image_path: list[str] = []

        def mock_ocr_extract(image_path: str) -> str:
            captured_image_path.append(image_path)
            return "Mock OCR text"

        mock_ocr_provider = MagicMock()
        mock_ocr_provider.extract_text = mock_ocr_extract

        mock_ai_provider = MagicMock()
        mock_ai_provider.analyze_image.return_value = {
            "caption": "test caption",
            "scene": "test scene",
            "action": "test action",
        }

        mock_embedding_provider = MagicMock()
        mock_embedding_provider.embed_text.return_value = np.zeros(
            1024, dtype=np.float32
        )

        mock_vector_store = MagicMock()
        mock_sql_store = MagicMock()
        mock_sql_store.mark_task_completed.return_value = True

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))

        with (
            patch("openrecall.server.worker.runtime_settings") as mock_runtime,
            patch("openrecall.server.worker.settings") as mock_settings,
        ):
            mock_runtime.ai_processing_enabled = True
            mock_runtime.ai_processing_version = 1
            mock_runtime._lock = MockLock()

            mock_settings.screenshots_path = screenshots_dir
            mock_settings.debug = False
            mock_settings.embedding_dim = 1024
            mock_settings.fusion_log_enabled = False

            worker = ProcessingWorker()
            worker._process_task(
                conn,
                task,
                mock_ai_provider,
                mock_ocr_provider,
                mock_embedding_provider,
                mock_vector_store,
                mock_sql_store,
                ai_processing_version=1,
            )

        conn.close()

        assert len(captured_image_path) == 1
        assert captured_image_path[0] == str(test_image_path)

    def test_worker_fails_when_image_relpath_file_not_found(
        self, tmp_path: Path
    ) -> None:
        """Worker marks task as failed when image_relpath points to missing file."""
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        from openrecall.shared.models import RecallEntry
        from openrecall.server.worker import ProcessingWorker

        task = RecallEntry(
            id=3,
            timestamp=1234567890,
            app="TestApp",
            title="Test Window",
            status="PENDING",
            device_id="test-device",
            image_relpath="test-device/nonexistent.png",
        )

        mock_ocr_provider = MagicMock()
        mock_ai_provider = MagicMock()
        mock_embedding_provider = MagicMock()
        mock_vector_store = MagicMock()
        mock_sql_store = MagicMock()

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))

        with (
            patch("openrecall.server.worker.runtime_settings") as mock_runtime,
            patch("openrecall.server.worker.settings") as mock_settings,
        ):
            mock_runtime.ai_processing_enabled = True
            mock_runtime.ai_processing_version = 1
            mock_runtime._lock = MockLock()

            mock_settings.screenshots_path = screenshots_dir
            mock_settings.debug = False

            worker = ProcessingWorker()
            worker._process_task(
                conn,
                task,
                mock_ai_provider,
                mock_ocr_provider,
                mock_embedding_provider,
                mock_vector_store,
                mock_sql_store,
                ai_processing_version=1,
            )

        conn.close()

        mock_sql_store.mark_task_failed.assert_called_once_with(conn, 3)
        mock_ocr_provider.extract_text.assert_not_called()
