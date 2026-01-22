import types
import numpy as np
from unittest.mock import patch
import torch
import pytest


class _DummyInputs(dict):
    def __init__(self, input_ids, attention_mask):
        super().__init__(input_ids=input_ids, attention_mask=attention_mask)
        self.input_ids = input_ids
        self.attention_mask = attention_mask

    def to(self, device):
        return self


class _DummyProcessor:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        return "prompt"

    def __call__(self, text=None, images=None, videos=None, padding=True, return_tensors="pt"):
        input_ids = torch.tensor([[1, 2, 3, 4]], dtype=torch.long)
        attention_mask = torch.tensor([[1, 1, 1, 1]], dtype=torch.long)
        return _DummyInputs(input_ids=input_ids, attention_mask=attention_mask)


class _DummyModel:
    def __init__(self):
        self.device = "cpu"

    def __call__(self, **kwargs):
        last = torch.zeros((1, 4, 4), dtype=torch.float32)
        last[0, 3, :] = torch.tensor([1.0, 2.0, 3.0, 4.0], dtype=torch.float32)
        out = types.SimpleNamespace()
        out.hidden_states = [last]
        return out


def test_local_mm_embedding_provider_returns_normalized_vector():
    from openrecall.server.ai import providers

    def fake_process_vision_info(messages):
        return None, None

    with patch.object(providers, "Qwen3VLForConditionalGeneration") as m, patch.object(
        providers, "AutoProcessor"
    ) as p, patch.object(providers, "process_vision_info", side_effect=fake_process_vision_info):
        m.from_pretrained.return_value = _DummyModel()
        p.from_pretrained.return_value = _DummyProcessor()
        prov = providers.LocalMMEmbeddingProvider(model_name="/tmp/model")
        vec = prov.embed_text("hello")
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (int(providers.settings.embedding_dim),)
        assert float(np.linalg.norm(vec)) == pytest.approx(1.0, rel=1e-5, abs=1e-6)


def test_local_mm_embedding_provider_empty_text_is_zero():
    from openrecall.server.ai import providers

    with patch.object(providers, "Qwen3VLForConditionalGeneration") as m, patch.object(
        providers, "AutoProcessor"
    ) as p:
        m.from_pretrained.return_value = _DummyModel()
        p.from_pretrained.return_value = _DummyProcessor()
        prov = providers.LocalMMEmbeddingProvider(model_name="/tmp/model")
        vec = prov.embed_text("")
        assert float(np.linalg.norm(vec)) == 0.0
