"""
Unit tests for P1-S2b+ Simhash trigger-type configuration.

This test module validates:
- simhash_enabled_for_click configuration
- simhash_enabled_for_app_switch configuration
- min_capture_interval_ms default value (2000ms)
- Simhash dedup logic respects trigger type configuration
"""

import pytest

from openrecall.client.events.base import CaptureTrigger


class TestSimhashTriggerConfig:
    """Tests for simhash trigger-type configuration."""

    def test_simhash_enabled_for_click_default(self):
        """simhash_enabled_for_click should default to True."""
        from openrecall.shared.config import Settings

        settings = Settings()
        assert settings.simhash_enabled_for_click is True

    def test_simhash_enabled_for_app_switch_default(self):
        """simhash_enabled_for_app_switch should default to False for performance."""
        from openrecall.shared.config import Settings

        settings = Settings()
        assert settings.simhash_enabled_for_app_switch is False

    def test_simhash_enabled_for_click_can_be_disabled(self, monkeypatch):
        """simhash_enabled_for_click should be configurable via env."""
        monkeypatch.setenv("OPENRECALL_SIMHASH_ENABLED_FOR_CLICK", "false")
        from openrecall.shared.config import Settings

        settings = Settings()
        assert settings.simhash_enabled_for_click is False

    def test_simhash_enabled_for_app_switch_can_be_enabled(self, monkeypatch):
        """simhash_enabled_for_app_switch should be configurable via env to enable."""
        monkeypatch.setenv("OPENRECALL_SIMHASH_ENABLED_FOR_APP_SWITCH", "true")
        from openrecall.shared.config import Settings

        settings = Settings()
        assert settings.simhash_enabled_for_app_switch is True


class TestDebounceConfig:
    """Tests for debounce interval configuration."""

    def test_min_capture_interval_default_2000ms(self):
        """min_capture_interval_ms should default to 2000ms."""
        from openrecall.shared.config import Settings

        settings = Settings()
        assert settings.min_capture_interval_ms == 2000

    def test_min_capture_interval_configurable(self, monkeypatch):
        """min_capture_interval_ms should be configurable via env."""
        monkeypatch.setenv("OPENRECALL_MIN_CAPTURE_INTERVAL_MS", "3000")
        from openrecall.shared.config import Settings

        settings = Settings()
        assert settings.min_capture_interval_ms == 3000


class TestSimhashTriggerTypeLogic:
    """Tests for simhash trigger-type check logic."""

    def test_idle_always_skips_simhash(self):
        """IDLE trigger should always skip simhash check."""
        from openrecall.shared.config import Settings

        settings = Settings()

        # Simulate the logic
        trigger = CaptureTrigger.IDLE
        should_check = (
            trigger != CaptureTrigger.IDLE
            and (
                (trigger == CaptureTrigger.CLICK and settings.simhash_enabled_for_click)
                or (trigger == CaptureTrigger.APP_SWITCH and settings.simhash_enabled_for_app_switch)
            )
        )
        assert should_check is False

    def test_click_respects_config_enabled(self):
        """CLICK trigger should check simhash when enabled."""
        from openrecall.shared.config import Settings

        settings = Settings()

        trigger = CaptureTrigger.CLICK
        should_check = (
            trigger != CaptureTrigger.IDLE
            and (
                (trigger == CaptureTrigger.CLICK and settings.simhash_enabled_for_click)
                or (trigger == CaptureTrigger.APP_SWITCH and settings.simhash_enabled_for_app_switch)
            )
        )
        assert should_check is True

    def test_click_respects_config_disabled(self, monkeypatch):
        """CLICK trigger should skip simhash when disabled."""
        monkeypatch.setenv("OPENRECALL_SIMHASH_ENABLED_FOR_CLICK", "false")
        from openrecall.shared.config import Settings

        settings = Settings()

        trigger = CaptureTrigger.CLICK
        should_check = (
            trigger != CaptureTrigger.IDLE
            and (
                (trigger == CaptureTrigger.CLICK and settings.simhash_enabled_for_click)
                or (trigger == CaptureTrigger.APP_SWITCH and settings.simhash_enabled_for_app_switch)
            )
        )
        assert should_check is False

    def test_app_switch_respects_config_enabled(self, monkeypatch):
        """APP_SWITCH trigger should check simhash when explicitly enabled."""
        monkeypatch.setenv("OPENRECALL_SIMHASH_ENABLED_FOR_APP_SWITCH", "true")
        from openrecall.shared.config import Settings

        settings = Settings()

        trigger = CaptureTrigger.APP_SWITCH
        should_check = (
            trigger != CaptureTrigger.IDLE
            and (
                (trigger == CaptureTrigger.CLICK and settings.simhash_enabled_for_click)
                or (trigger == CaptureTrigger.APP_SWITCH and settings.simhash_enabled_for_app_switch)
            )
        )
        assert should_check is True

    def test_app_switch_respects_config_disabled(self):
        """APP_SWITCH trigger should skip simhash when disabled (default)."""
        from openrecall.shared.config import Settings

        settings = Settings()

        trigger = CaptureTrigger.APP_SWITCH
        should_check = (
            trigger != CaptureTrigger.IDLE
            and (
                (trigger == CaptureTrigger.CLICK and settings.simhash_enabled_for_click)
                or (trigger == CaptureTrigger.APP_SWITCH and settings.simhash_enabled_for_app_switch)
            )
        )
        assert should_check is False


class TestHeartbeatConfigRemoved:
    """Tests to verify heartbeat configuration is removed."""

    def test_simhash_heartbeat_interval_removed(self):
        """simhash_heartbeat_interval_sec should not exist in Settings."""
        from openrecall.shared.config import Settings

        settings = Settings()
        # Should not have this attribute
        assert not hasattr(settings, "simhash_heartbeat_interval_sec")