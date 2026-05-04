import pytest
from unittest.mock import MagicMock, patch

from openrecall.server.description.worker import DescriptionWorker
from openrecall.server.config_runtime import runtime_settings


@pytest.fixture(autouse=True)
def _reset_ai_processing_version():
    """Save and restore the global runtime_settings.ai_processing_version."""
    saved = runtime_settings.ai_processing_version
    yield
    with runtime_settings._lock:
        runtime_settings.ai_processing_version = saved


class TestDescriptionWorkerHotReload:
    def test_service_is_none_on_init(self):
        store = MagicMock()
        worker = DescriptionWorker(store)
        assert worker._service is None
        assert worker._last_processing_version == -1

    def test_version_bump_triggers_service_reset(self):
        store = MagicMock()
        store._connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
        store._connect.return_value.__exit__ = MagicMock(return_value=False)
        store.claim_description_task.return_value = None  # no tasks

        worker = DescriptionWorker(store)
        worker._service = MagicMock()  # pretend service exists
        worker._last_processing_version = runtime_settings.ai_processing_version

        # Simulate external version bump
        runtime_settings.bump_ai_processing_version()
        new_version = runtime_settings.ai_processing_version

        # Call _process_batch — should detect version change and reset service
        with patch.object(worker, '_log_queue_status'):
            worker._process_batch(MagicMock())

        assert worker._service is None
        assert worker._last_processing_version == new_version

    def test_no_reset_when_version_unchanged(self):
        store = MagicMock()
        store._connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
        store._connect.return_value.__exit__ = MagicMock(return_value=False)
        store.claim_description_task.return_value = None

        worker = DescriptionWorker(store)
        fake_service = MagicMock()
        worker._service = fake_service
        worker._last_processing_version = runtime_settings.ai_processing_version

        with patch.object(worker, '_log_queue_status'):
            worker._process_batch(MagicMock())

        assert worker._service is fake_service  # unchanged
