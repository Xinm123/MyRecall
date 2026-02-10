import sys
import os
import tempfile
import types
from pathlib import Path
import importlib

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_DEFAULT_TEST_DATA_DIR = tempfile.mkdtemp(prefix="openrecall_test_data_")
os.environ.setdefault("OPENRECALL_DATA_DIR", _DEFAULT_TEST_DATA_DIR)


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    # Reload sql submodule so it picks up new settings
    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    # SQLStore() auto-initializes the database in __init__
    openrecall.server.database.SQLStore()

    import openrecall.server.auth
    importlib.reload(openrecall.server.auth)

    # Mock SearchEngine to avoid HuggingFace model download in test env
    import unittest.mock as mock
    if "qwen_vl_utils" not in sys.modules:
        qwen_stub = types.ModuleType("qwen_vl_utils")
        qwen_stub.process_vision_info = lambda *_args, **_kwargs: ([], [])
        sys.modules["qwen_vl_utils"] = qwen_stub
    if "openrecall.server.ai.providers" not in sys.modules:
        providers_stub = types.ModuleType("openrecall.server.ai.providers")

        class _DummyProvider:
            def __init__(self, *_args, **_kwargs):
                pass

        for name in (
            "DashScopeEmbeddingProvider",
            "DashScopeOCRProvider",
            "DashScopeProvider",
            "DoctrOCRProvider",
            "LocalEmbeddingProvider",
            "LocalOCRProvider",
            "LocalProvider",
            "OpenAIEmbeddingProvider",
            "OpenAIOCRProvider",
            "OpenAIProvider",
            "RapidOCRProvider",
        ):
            setattr(providers_stub, name, _DummyProvider)
        sys.modules["openrecall.server.ai.providers"] = providers_stub
    import openrecall.server.search.engine
    mock_se = mock.MagicMock()
    mock_se.search.return_value = []
    monkeypatch.setattr(
        openrecall.server.search.engine, "SearchEngine", lambda: mock_se
    )

    import openrecall.server.api
    importlib.reload(openrecall.server.api)

    import openrecall.server.api_v1
    importlib.reload(openrecall.server.api_v1)

    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    return openrecall.server.app.app


@pytest.fixture
def flask_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
