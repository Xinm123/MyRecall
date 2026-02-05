import importlib
from typing import cast


def _reload_settings(monkeypatch, tmp_path):
    server_dir = tmp_path / "server"
    client_dir = tmp_path / "client"
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    return openrecall.shared.config.settings


class DummyVectorStore:
    last_device_id = None

    def __init__(self, device_id: str = "legacy"):
        DummyVectorStore.last_device_id = device_id
        self.device_id = device_id

    def search(self, query_vec, limit: int = 10, where: str | None = None):
        return []

    def get_snapshots(self, ids):
        return []


class DummySQLStore:
    def __init__(self):
        self.last_device_id = None

    def search(self, query: str, limit: int = 10, device_id: str | None = None):
        self.last_device_id = device_id
        return []


class DummyEmbeddingProvider:
    def embed_text(self, text: str):
        return [0.1, 0.2, 0.3]


class DummyReranker:
    def compute_score(self, query: str, docs):
        return [0.0] * len(docs)


def test_search_engine_uses_device_scoped_vector_and_fts_paths(tmp_path, monkeypatch):
    _reload_settings(monkeypatch, tmp_path)

    import openrecall.server.search.engine as engine_module

    importlib.reload(engine_module)

    monkeypatch.setattr(
        engine_module, "get_ai_provider", lambda _mode: DummyEmbeddingProvider()
    )
    monkeypatch.setattr(engine_module, "get_reranker", lambda: DummyReranker())
    monkeypatch.setattr(engine_module, "VectorStore", DummyVectorStore)
    monkeypatch.setattr(engine_module, "SQLStore", DummySQLStore)

    engine = engine_module.SearchEngine()

    engine.search("hello", limit=1, device_id="device-a")

    assert DummyVectorStore.last_device_id == "device-a"
    sql_store = cast(DummySQLStore, cast(object, engine.sql_store))
    assert sql_store.last_device_id == "device-a"


def test_vector_store_creates_device_specific_directory(tmp_path, monkeypatch):
    settings = _reload_settings(monkeypatch, tmp_path)

    import openrecall.server.database.vector_store as vector_module

    importlib.reload(vector_module)

    store = vector_module.VectorStore(device_id="device-a")
    expected_path = settings.lancedb_path / "device-a"

    assert store.db_path == expected_path
    assert expected_path.exists()


def test_fts_uses_device_specific_db_file(tmp_path, monkeypatch):
    settings = _reload_settings(monkeypatch, tmp_path)

    import openrecall.server.database.sql as sql_module

    importlib.reload(sql_module)

    store = sql_module.SQLStore()
    store.add_document(
        "snap-1",
        "ocr text",
        "caption",
        ["keyword"],
        device_id="device-a",
    )

    expected_path = settings.server_data_dir / "fts" / "device-a.db"

    assert sql_module.SQLStore.get_fts_path("device-a") == expected_path
    assert expected_path.exists()
