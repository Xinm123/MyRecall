import importlib

import numpy as np
import pytest


def test_cache_vector_backend_query_top1():
    from openrecall.server.vector_backend import CacheVectorBackend

    backend = CacheVectorBackend()
    backend.upsert(1, np.array([1.0, 0.0, 0.0], dtype=np.float32))
    backend.upsert(2, np.array([0.0, 1.0, 0.0], dtype=np.float32))

    hits = backend.query(np.array([1.0, 0.0, 0.0], dtype=np.float32), topk=1)
    assert hits[0][0] == 1
    assert hits[0][1] > 0.9


def test_get_vector_backend_falls_back_when_sqlite_vss_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_VECTOR_BACKEND", "sqlite_vss")

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.vector_backend
    importlib.reload(openrecall.server.vector_backend)

    backend = openrecall.server.vector_backend.get_vector_backend()
    assert backend.__class__.__name__ == "CacheVectorBackend"


def test_sqlite_vss_backend_smoke_if_available(monkeypatch, tmp_path):
    try:
        import sqlite_vss  # type: ignore

        _ = sqlite_vss
        has_vss = True
    except Exception:
        has_vss = False
    if not has_vss:
        pytest.skip("sqlite_vss not installed")

    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_VECTOR_BACKEND", "sqlite_vss")

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.vector_backend
    importlib.reload(openrecall.server.vector_backend)

    backend = openrecall.server.vector_backend.get_vector_backend()
    backend.bulk_upsert(
        [
            (1, np.array([1.0, 0.0, 0.0], dtype=np.float32)),
            (2, np.array([0.0, 1.0, 0.0], dtype=np.float32)),
        ]
    )
    hits = backend.query(np.array([1.0, 0.0, 0.0], dtype=np.float32), topk=1)
    assert hits[0][0] == 1
