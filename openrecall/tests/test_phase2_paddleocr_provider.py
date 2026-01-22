import importlib

import pytest


def test_paddleocr_provider_optional_dependency(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_OCR_PROVIDER", "paddleocr")

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.ai.factory
    importlib.reload(openrecall.server.ai.factory)

    from openrecall.server.ai.base import AIProviderUnavailableError
    provider = openrecall.server.ai.factory.get_ocr_provider()
    from PIL import Image

    image_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 100), color=(255, 255, 255)).save(image_path)
    try:
        import paddleocr  # type: ignore
        _ = paddleocr
        has_paddleocr = True
    except Exception:
        has_paddleocr = False

    if not has_paddleocr:
        with pytest.raises(AIProviderUnavailableError):
            provider.extract_text(str(image_path))
        return

    out = provider.extract_text(str(image_path))
    assert isinstance(out, str)
