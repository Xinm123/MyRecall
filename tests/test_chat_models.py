from openrecall.client.chat.models import DEFAULT_PROVIDER, DEFAULT_MODEL  # noqa: F401


def test_default_provider():
    assert DEFAULT_PROVIDER == "minimax-cn"


def test_default_model():
    assert DEFAULT_MODEL == "MiniMax-M2.7"
