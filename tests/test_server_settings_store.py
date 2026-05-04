import pytest
from pathlib import Path
from openrecall.server.database.settings_store import ServerSettingsStore


class TestServerSettingsStore:
    def test_init_creates_table_no_defaults(self, tmp_path):
        """Init creates table; does NOT pre-insert default rows."""
        db_path = tmp_path / "settings.db"
        store = ServerSettingsStore(db_path)
        assert db_path.exists()
        # Table should be empty on first run
        assert store.get_all() == {}

    def test_set_get_round_trip(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        assert store.get("description.provider") == "openai"

    def test_two_sets_same_key_last_wins(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.provider", "dashscope")
        assert store.get("description.provider") == "dashscope"

    def test_delete_then_get_returns_none(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.delete("description.provider")
        assert store.get("description.provider") is None

    def test_get_all_returns_only_existing_rows(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        assert store.get_all() == {}
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        assert store.get_all() == {
            "description.provider": "openai",
            "description.model": "gpt-4o",
        }

    def test_get_with_explicit_default(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        assert store.get("missing", default="fallback") == "fallback"

    def test_reset_to_defaults_deletes_description_keys(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        store.set("other.key", "value")  # not a description key
        store.reset_to_defaults()
        assert store.get("description.provider") is None
        assert store.get("description.model") is None
        assert store.get("other.key") == "value"  # untouched

    def test_reset_to_defaults_on_empty_db_is_noop(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.reset_to_defaults()
        assert store.get_all() == {}

    def test_reset_to_defaults_leaves_get_all_empty(self, tmp_path):
        """When only description keys exist, reset makes get_all return {}."""
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        assert store.get_all() != {}
        store.reset_to_defaults()
        assert store.get_all() == {}

    def test_auto_creates_parent_dir(self, tmp_path):
        db_path = tmp_path / "deep" / "nested" / "settings.db"
        store = ServerSettingsStore(db_path)
        assert db_path.exists()

    def test_non_string_value_coerced(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.request_timeout", 120)  # int
        assert store.get("description.request_timeout") == "120"

    def test_set_many_atomic(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set_many({
            "description.provider": "openai",
            "description.model": "gpt-4o",
            "description.api_key": "sk-test",
        })
        assert store.get("description.provider") == "openai"
        assert store.get("description.model") == "gpt-4o"
        assert store.get("description.api_key") == "sk-test"

    def test_apply_changes_atomic(self, tmp_path):
        """apply_changes performs deletes + sets in a single transaction."""
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.set("description.model", "gpt-4o")
        store.set("description.api_base", "https://api.openai.com/v1")

        store.apply_changes(
            deletes=["description.provider", "description.model"],
            sets={"description.api_key": "sk-newkey"},
        )

        assert store.get("description.provider") is None
        assert store.get("description.model") is None
        assert store.get("description.api_base") == "https://api.openai.com/v1"
        assert store.get("description.api_key") == "sk-newkey"

    def test_apply_changes_empty_is_noop(self, tmp_path):
        store = ServerSettingsStore(tmp_path / "settings.db")
        store.set("description.provider", "openai")
        store.apply_changes(deletes=[], sets={})
        assert store.get("description.provider") == "openai"
