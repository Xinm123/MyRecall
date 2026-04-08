"""Settings API routes for client Web UI."""

import logging
from pathlib import Path
from typing import Optional

import requests
from flask import Blueprint, jsonify, request

from openrecall.client.database import ClientSettingsStore
from openrecall.shared.config import settings as app_settings

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/client")

# Lazy initialization of settings store (to ensure TOML config is loaded first)
_settings_store: Optional[ClientSettingsStore] = None


def get_settings_store() -> ClientSettingsStore:
    """Get the settings store instance.

    Lazily initialized to ensure TOML config is loaded before accessing paths.
    """
    global _settings_store
    if _settings_store is None:
        db_path = Path(app_settings.client_data_dir) / "client.db"
        _settings_store = ClientSettingsStore(db_path)
    return _settings_store


@settings_bp.route("/settings", methods=["GET"])
def get_settings():
    """Get all client settings.

    Returns:
        JSON object with all settings as key-value pairs
    """
    store = get_settings_store()
    settings = store.get_all()
    return jsonify(settings)


@settings_bp.route("/settings", methods=["POST"])
def update_settings():
    """Update one or more client settings.

    Request body:
        JSON object with settings to update

    Returns:
        JSON object with updated settings
    """
    store = get_settings_store()
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    # Validate settings
    validators = {
        "edge_base_url": lambda v: v is None or v == "" or v.startswith(("http://", "https://")),
        "capture_save_local_copies": lambda v: str(v).lower() in ("true", "false"),
        "capture_permission_poll_sec": lambda v: str(v).isdigit() and 1 <= int(v) <= 300,
        "debounce.click_ms": lambda v: str(v).isdigit() and 0 <= int(v) <= 60000,
        "debounce.trigger_ms": lambda v: str(v).isdigit() and 0 <= int(v) <= 60000,
        "debounce.capture_ms": lambda v: str(v).isdigit() and 0 <= int(v) <= 60000,
        "debounce.idle_interval_ms": lambda v: str(v).isdigit() and 10000 <= int(v) <= 600000,
        "stats.interval_sec": lambda v: str(v).isdigit() and 10 <= int(v) <= 3600,
    }

    for key, value in data.items():
        if key in validators and not validators[key](value):
            return jsonify({"error": f"Invalid value for {key}"}), 400

    # Update settings
    for key, value in data.items():
        store.set(key, str(value))
        logger.info(f"Setting updated via API: {key}")

    return jsonify(store.get_all())


@settings_bp.route("/settings/reset", methods=["POST"])
def reset_settings():
    """Reset all settings to default values.

    Returns:
        JSON object with default settings
    """
    store = get_settings_store()
    store.reset_to_defaults()
    return jsonify(store.get_all())


@settings_bp.route("/settings/edge/health", methods=["GET"])
def test_edge_connection():
    """Test connection to the configured Edge server.

    Query parameters:
        url: Optional URL to test (uses configured edge_base_url if not provided)

    Returns:
        JSON object with connection status
    """
    store = get_settings_store()

    # Get URL from query param or from settings
    test_url = request.args.get("url") or store.get("edge_base_url")

    if not test_url:
        # Fallback to derived URL from app settings
        test_url = app_settings.edge_base_url

    if not test_url:
        return jsonify({
            "reachable": False,
            "error": "No Edge URL configured",
        }), 400

    health_url = f"{test_url.rstrip('/')}/v1/health"

    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "reachable": True,
                "status": data.get("status", "unknown"),
                "url": test_url,
            })
        else:
            return jsonify({
                "reachable": False,
                "error": f"HTTP {response.status_code}",
                "url": test_url,
            }), 502
    except requests.RequestException as e:
        return jsonify({
            "reachable": False,
            "error": str(e),
            "url": test_url,
        }), 502
