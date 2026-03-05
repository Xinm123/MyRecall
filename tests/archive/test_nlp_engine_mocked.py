import numpy as np


def test_nlp_engine_encode_empty_text_returns_zero(monkeypatch):
    import openrecall.server.nlp as nlp

    class DummyModel:
        def encode(self, *args, **kwargs):
            return np.ones((8,), dtype=np.float32)

    monkeypatch.setattr(nlp, "SentenceTransformer", lambda *a, **k: DummyModel())
    monkeypatch.setattr(nlp.settings, "embedding_dim", 8)
    monkeypatch.setattr(nlp.settings, "embedding_model_name", "dummy")
    monkeypatch.setattr(nlp.settings, "device", "cpu")

    engine = nlp.NLPEngine()
    out = engine.encode("   ")
    assert out.shape == (8,)
    assert float(out.sum()) == 0.0


def test_nlp_engine_encode_success(monkeypatch):
    import openrecall.server.nlp as nlp

    class DummyModel:
        def encode(self, text, normalize_embeddings=True):
            return np.arange(8, dtype=np.float32)

    monkeypatch.setattr(nlp, "SentenceTransformer", lambda *a, **k: DummyModel())
    monkeypatch.setattr(nlp.settings, "embedding_dim", 8)
    monkeypatch.setattr(nlp.settings, "embedding_model_name", "dummy")
    monkeypatch.setattr(nlp.settings, "device", "cpu")

    engine = nlp.NLPEngine()
    out = engine.encode("hello")
    assert out.dtype == np.float32
    assert out.shape == (8,)
    assert float(out[1]) == 1.0


def test_nlp_engine_encode_exception_returns_zero(monkeypatch):
    import openrecall.server.nlp as nlp

    class DummyModel:
        def encode(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(nlp, "SentenceTransformer", lambda *a, **k: DummyModel())
    monkeypatch.setattr(nlp.settings, "embedding_dim", 8)
    monkeypatch.setattr(nlp.settings, "embedding_model_name", "dummy")
    monkeypatch.setattr(nlp.settings, "device", "cpu")

    engine = nlp.NLPEngine()
    out = engine.encode("hello")
    assert float(out.sum()) == 0.0


def test_get_nlp_engine_caches_instance(monkeypatch):
    import openrecall.server.nlp as nlp

    class DummyModel:
        def encode(self, *args, **kwargs):
            return np.zeros((8,), dtype=np.float32)

    monkeypatch.setattr(nlp, "SentenceTransformer", lambda *a, **k: DummyModel())
    monkeypatch.setattr(nlp.settings, "embedding_dim", 8)
    monkeypatch.setattr(nlp.settings, "embedding_model_name", "dummy")
    monkeypatch.setattr(nlp.settings, "device", "cpu")

    nlp._engine = None
    e1 = nlp.get_nlp_engine()
    e2 = nlp.get_nlp_engine()
    assert e1 is e2


def test_get_embedding_uses_singleton(monkeypatch):
    import openrecall.server.nlp as nlp

    class DummyModel:
        def encode(self, *args, **kwargs):
            return np.zeros((8,), dtype=np.float32)

    monkeypatch.setattr(nlp, "SentenceTransformer", lambda *a, **k: DummyModel())
    monkeypatch.setattr(nlp.settings, "embedding_dim", 8)
    monkeypatch.setattr(nlp.settings, "embedding_model_name", "dummy")
    monkeypatch.setattr(nlp.settings, "device", "cpu")

    nlp._engine = None
    emb = nlp.get_embedding("hello")
    assert emb.shape == (8,)

