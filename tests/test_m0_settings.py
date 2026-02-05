import json

from openrecall.shared.config import Settings


def _set_tmp_dirs(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "server"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "client"))


def test_settings_auth_mode_defaults_to_strict(monkeypatch, tmp_path) -> None:
    _set_tmp_dirs(monkeypatch, tmp_path)

    settings = Settings()

    assert settings.auth_mode == "strict"


def test_settings_device_tokens_json_parses_correctly(monkeypatch, tmp_path) -> None:
    _set_tmp_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "OPENRECALL_DEVICE_TOKENS_JSON",
        json.dumps({"device-a": {"token": "abc123"}}),
    )

    settings = Settings()

    assert json.loads(settings.device_tokens_json) == {"device-a": {"token": "abc123"}}


def test_settings_legacy_device_id_defaults_to_legacy(monkeypatch, tmp_path) -> None:
    _set_tmp_dirs(monkeypatch, tmp_path)

    settings = Settings()

    assert settings.legacy_device_id == "legacy"
