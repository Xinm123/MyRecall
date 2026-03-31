import sys
import os
import tempfile
from pathlib import Path
import importlib
import sqlite3

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_DEFAULT_TEST_DATA_DIR = tempfile.mkdtemp(prefix="openrecall_test_data_")
os.environ.setdefault("OPENRECALL_DATA_DIR", _DEFAULT_TEST_DATA_DIR)


def pytest_configure(config):
    """Initialize settings BEFORE test collection so all modules get the real settings."""
    import openrecall.shared.config

    # Reload to ensure clean state
    importlib.reload(openrecall.shared.config)

    # Initialize settings with test data dir
    from openrecall.server.config_server import ServerSettings

    test_settings = ServerSettings.from_toml()
    openrecall.shared.config.settings = test_settings


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)

    import openrecall.server.database

    importlib.reload(openrecall.server.database)
    # SQLStore() auto-initializes the entries/fts databases
    openrecall.server.database.SQLStore()

    # Run v3 migrations on the same DB path settings uses
    from openrecall.server.database.frames_store import FramesStore
    from openrecall.server.database.migrations_runner import run_migrations

    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    db_path = openrecall.shared.config.settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        run_migrations(conn, migrations_dir)

    # Create FramesStore and patch into api_v1
    store = FramesStore(db_path=db_path)

    import openrecall.server.api_v1 as api_v1

    original_store = api_v1._frames_store
    api_v1._frames_store = store

    import openrecall.server.api

    importlib.reload(openrecall.server.api)

    import openrecall.server.app

    importlib.reload(openrecall.server.app)

    yield openrecall.server.app.app

    # Restore
    api_v1._frames_store = original_store


@pytest.fixture
def flask_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
