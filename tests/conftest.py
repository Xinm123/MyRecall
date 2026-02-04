import sys
import os
import tempfile
from pathlib import Path
import importlib

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_DEFAULT_TEST_DATA_DIR = tempfile.mkdtemp(prefix="openrecall_test_data_")
_DEFAULT_TEST_CLIENT_DIR = tempfile.mkdtemp(prefix="openrecall_test_client_")
os.environ.setdefault("OPENRECALL_ROLE", "combined")
os.environ.setdefault("OPENRECALL_SERVER_DATA_DIR", _DEFAULT_TEST_DATA_DIR)
os.environ.setdefault("OPENRECALL_CLIENT_DATA_DIR", _DEFAULT_TEST_CLIENT_DIR)


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    client_dir = tmp_path / "client"

    monkeypatch.setenv("OPENRECALL_ROLE", "combined")
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)

    import openrecall.server.database

    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    import openrecall.server.api

    importlib.reload(openrecall.server.api)

    import openrecall.server.app

    importlib.reload(openrecall.server.app)

    return openrecall.server.app.app


@pytest.fixture
def flask_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
