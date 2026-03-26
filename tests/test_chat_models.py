from openrecall.client.chat.models import DEFAULT_PROVIDER, DEFAULT_MODEL  # noqa: F401


def test_default_provider():
    assert DEFAULT_PROVIDER == "qianfan"


def test_default_model():
    assert DEFAULT_MODEL == "deepseek-r1-250528"
