"""Tests for DescriptionWorker."""
import pytest
from unittest.mock import MagicMock


class TestDescriptionWorker:
    def test_worker_starts_and_stops(self):
        from openrecall.server.description.worker import DescriptionWorker

        mock_store = MagicMock()
        worker = DescriptionWorker(store=mock_store, poll_interval=0.1)
        assert worker.name == "DescriptionWorker"
        assert worker.daemon is True

    def test_worker_initializes_store(self):
        from openrecall.server.description.worker import DescriptionWorker

        mock_store = MagicMock()
        worker = DescriptionWorker(store=mock_store)
        assert worker._store is mock_store

    def test_worker_stop_event(self):
        from openrecall.server.description.worker import DescriptionWorker

        mock_store = MagicMock()
        worker = DescriptionWorker(store=mock_store, poll_interval=0.1)
        assert not worker._stop_event.is_set()
        worker.stop()
        assert worker._stop_event.is_set()
