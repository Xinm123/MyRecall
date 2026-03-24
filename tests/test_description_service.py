"""Tests for DescriptionService."""
from unittest.mock import MagicMock, patch

import pytest


class TestDescriptionService:
    def test_enqueue_is_idempotent(self):
        from openrecall.server.description.service import DescriptionService

        mock_store = MagicMock()
        svc = DescriptionService(store=mock_store)
        mock_conn = MagicMock()
        svc.enqueue_description_task(mock_conn, frame_id=1)
        mock_store.insert_description_task.assert_called_once_with(mock_conn, 1)

    def test_service_initializes_without_provider(self):
        from openrecall.server.description.service import DescriptionService

        mock_store = MagicMock()
        svc = DescriptionService(store=mock_store)
        # Provider should not be loaded until accessed
        assert svc._provider is None

    def test_backfill_calls_store_method(self):
        from openrecall.server.description.service import DescriptionService

        mock_store = MagicMock()
        mock_store.enqueue_pending_descriptions.return_value = 5
        svc = DescriptionService(store=mock_store)
        mock_conn = MagicMock()
        count = svc.backfill(mock_conn)
        assert count == 5
        mock_store.enqueue_pending_descriptions.assert_called_once_with(mock_conn)

    def test_get_queue_status_calls_store_method(self):
        from openrecall.server.description.service import DescriptionService

        mock_store = MagicMock()
        mock_store.get_description_queue_status.return_value = {
            "pending": 3,
            "completed": 10,
            "processing": 1,
            "failed": 0,
        }
        svc = DescriptionService(store=mock_store)
        mock_conn = MagicMock()
        status = svc.get_queue_status(mock_conn)
        assert status == {
            "pending": 3,
            "completed": 10,
            "processing": 1,
            "failed": 0,
        }
