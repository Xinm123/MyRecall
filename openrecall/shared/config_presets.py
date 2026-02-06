"""Deployment configuration presets for MyRecall v3.

Defines settings overrides for each deployment mode:
- local: Both client and server on same machine (default)
- remote: Both client and server, server accessible remotely
- debian_client: Client-only mode, connects to remote server
- debian_server: Server-only mode, binds to all interfaces
"""

from typing import Dict, Any

# Deployment preset definitions
PRESETS: Dict[str, Dict[str, Any]] = {
    "local": {
        "host": "127.0.0.1",
        "description": "Local development mode (client + server on same machine)",
        "runs_server": True,
        "runs_client": True,
    },
    "remote": {
        "host": "127.0.0.1",
        "description": "Remote mode (client + server, server accessible remotely)",
        "runs_server": True,
        "runs_client": True,
    },
    "debian_client": {
        "description": "Client-only mode (connects to remote server)",
        "runs_server": False,
        "runs_client": True,
    },
    "debian_server": {
        "host": "0.0.0.0",
        "description": "Server-only mode (binds to all interfaces)",
        "runs_server": True,
        "runs_client": False,
    },
}

VALID_MODES = set(PRESETS.keys())


def get_preset(mode: str) -> Dict[str, Any]:
    """Get the preset configuration for a deployment mode.

    Args:
        mode: One of 'local', 'remote', 'debian_client', 'debian_server'.

    Returns:
        Dict of settings overrides for the given mode.

    Raises:
        ValueError: If mode is not a valid deployment mode.
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid deployment mode: '{mode}'. "
            f"Valid modes: {sorted(VALID_MODES)}"
        )
    return PRESETS[mode].copy()


def apply_preset(settings, mode: str) -> None:
    """Apply deployment preset overrides to a Settings instance.

    Only overrides fields that the preset explicitly defines.
    Does not override fields already set via environment variables.

    Args:
        settings: A Settings instance to modify.
        mode: Deployment mode name.
    """
    preset = get_preset(mode)

    if "host" in preset:
        settings.host = preset["host"]
