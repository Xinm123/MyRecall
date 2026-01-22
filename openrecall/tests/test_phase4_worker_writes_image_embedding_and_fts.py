import importlib
import sqlite3
from unittest import mock

import numpy as np


def test_worker_writes_image_embedding_and_fts(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    settings = openrecall.shared.config.settings

    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    db = openrecall.server.database
    db.create_db()

    import openrecall.server.worker
    importlib.reload(openrecall.server.worker)

    from openrecall.server.config_runtime import runtime_settings

    with runtime_settings._lock:
        runtime_settings.ai_processing_enabled = True
        runtime_settings.ai_processing_version += 1
        version = runtime_settings.ai_processing_version

    ts = 1710000100
    task_id = db.insert_pending_entry(
        timestamp=ts,
        app="Terminal",
        title="npm ERR!",
        image_path=str(settings.screenshots_path / f"{ts}.png"),
    )
    assert task_id is not None

    from PIL import Image

    settings.screenshots_path.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color=(255, 255, 255)).save(settings.screenshots_path / f"{ts}.png")

    ai_provider = mock.MagicMock()
    ai_provider.analyze_image.return_value = "User debugging error"

    ocr_provider = mock.MagicMock()
    ocr_provider.extract_text.return_value = "TypeError: cannot read property"

    embedding_provider = mock.MagicMock()
    embedding_provider.embed_text.return_value = np.zeros(settings.embedding_dim, dtype=np.float32)

    mm_embedding_provider = mock.MagicMock()
    mm_embedding_provider.embed_image.return_value = np.ones(settings.embedding_dim, dtype=np.float32)

    conn = sqlite3.connect(str(settings.db_path))
    try:
        task = db.get_next_task(conn, lifo_mode=False)
        assert task is not None
        worker = openrecall.server.worker.ProcessingWorker()
        worker._process_task(
            conn,
            task,
            ai_provider,
            ocr_provider,
            embedding_provider,
            mm_embedding_provider,
            version,
        )
    finally:
        conn.close()

    entries = db.get_all_entries()
    assert len(entries) == 1
    assert entries[0].status == "COMPLETED"
    assert entries[0].image_embedding is not None
    assert np.allclose(entries[0].image_embedding, 1.0)

    with sqlite3.connect(str(settings.db_path)) as conn2:
        hits = db.fts_search(conn2, "TypeError", topk=5)
        assert hits
