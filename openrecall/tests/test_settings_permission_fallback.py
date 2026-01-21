def test_settings_falls_back_to_tmp_on_permission_error(monkeypatch, tmp_path):
    from openrecall.shared.config import Settings

    original = Settings.ensure_directories
    state = {"called": False}

    def boom_once(self):
        if not state["called"]:
            state["called"] = True
            raise PermissionError("nope")
        return original(self)

    monkeypatch.setattr(Settings, "ensure_directories", boom_once)
    s = Settings(OPENRECALL_DATA_DIR=str(tmp_path))
    assert s.base_path.name == "myrecall_data"
