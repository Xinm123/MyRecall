import sys
import os
import tempfile
from pathlib import Path
import importlib
import sqlite3

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_DEFAULT_TEST_DATA_DIR = tempfile.mkdtemp(prefix="myrecall_test_data_")
os.environ.setdefault("MYRECALL_DATA_DIR", _DEFAULT_TEST_DATA_DIR)


def pytest_configure(config):
    """Initialize settings BEFORE test collection so all modules get the real settings."""
    import myrecall.shared.config

    # Reload to ensure clean state
    importlib.reload(myrecall.shared.config)

    # Initialize settings with test data dir
    from myrecall.server.config_server import ServerSettings

    test_settings = ServerSettings.from_toml()
    myrecall.shared.config.settings = test_settings


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setenv("MYRECALL_DATA_DIR", str(tmp_path))

    import myrecall.shared.config

    importlib.reload(myrecall.shared.config)

    import myrecall.server.database

    importlib.reload(myrecall.server.database)
    # SQLStore() auto-initializes the entries/fts databases
    myrecall.server.database.SQLStore()

    # Run v3 migrations on the same DB path settings uses
    from myrecall.server.database.frames_store import FramesStore
    from myrecall.server.database.migrations_runner import run_migrations

    migrations_dir = Path(__file__).resolve().parent.parent / (
        "myrecall/server/database/migrations"
    )
    db_path = myrecall.shared.config.settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        run_migrations(conn, migrations_dir)

    # Create FramesStore and patch into api_v1
    store = FramesStore(db_path=db_path)

    import myrecall.server.api_v1 as api_v1

    original_store = api_v1._frames_store
    api_v1._frames_store = store

    import myrecall.server.api

    importlib.reload(myrecall.server.api)

    import myrecall.server.app

    importlib.reload(myrecall.server.app)

    yield myrecall.server.app.app

    # Restore
    api_v1._frames_store = original_store


@pytest.fixture
def flask_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
