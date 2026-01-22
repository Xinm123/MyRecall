import os
from unittest import mock

import numpy as np


def test_mm_embedding_config_defaults():
    from openrecall.shared.config import Settings
    with mock.patch.dict(os.environ, {}, clear=True):
        s = Settings()
        assert s.mm_embedding_provider in {"api", "local"}
        assert s.rerank_provider in {"api", "local"}
        assert s.vector_backend in {"cache", "sqlite_vss"}
        assert isinstance(s.hard_limit_recent_n, int) and s.hard_limit_recent_n > 0


def test_factory_mm_embedding_fallback():
    from openrecall.server.ai.factory import get_mm_embedding_provider
    from openrecall.shared.config import settings

    provider = get_mm_embedding_provider()
    vec_t = provider.embed_text("hello")
    vec_i = provider.embed_image("/non/existent.png")
    assert vec_t.shape == (settings.embedding_dim,)
    assert vec_i.shape == (settings.embedding_dim,)
    assert np.allclose(vec_t, 0)
    assert np.allclose(vec_i, 0)


def test_factory_reranker_fallback():
    from openrecall.server.ai.factory import get_reranker_provider
    provider = get_reranker_provider()
    out = provider.rerank("q", [{"id": 1}, {"id": 2}])
    assert isinstance(out, list)
    assert [c.get("id") for c in out] == [1, 2]
