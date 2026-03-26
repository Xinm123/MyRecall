"""
Config manager for Pi agent integration.

Phase 1 is READ-ONLY — this module does NOT write auth.json.
Users configure credentials via environment variables (MINIMAX_CN_API_KEY, KIMI_API_KEY).

Phase 4 (config UI) will add write functionality:
  - Atomic write to ~/.pi/agent/auth.json
  - Permissions 0o600
  - Merge-preserve other providers' keys
"""

import json
import os
from pathlib import Path
from typing import Optional


PI_CONFIG_DIR = Path.home() / ".pi" / "agent"
AUTH_JSON = PI_CONFIG_DIR / "auth.json"

# Provider name → environment variable name mapping
PROVIDER_ENV_MAP: dict[str, str] = {
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "kimi-coding": "KIMI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "qianfan": "QIANFAN_API_KEY",
    "custom": "CUSTOM_API_KEY",
}


def get_api_key(provider: str) -> Optional[str]:
    """
    Read API key for a given provider (informational/diagnostic use only).

    Priority:
      1. Environment variable (e.g. MINIMAX_CN_API_KEY)
      2. ~/.pi/agent/auth.json

    This is READ-ONLY. It does NOT write auth.json and does not affect Pi's
    actual credential resolution (Pi resolves credentials independently).
    """
    env_var = PROVIDER_ENV_MAP.get(provider)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]

    if AUTH_JSON.exists():
        try:
            auth_data = json.loads(AUTH_JSON.read_text())
            provider_data = auth_data.get(provider, {})
            return provider_data.get("key")
        except (json.JSONDecodeError, OSError):
            return None

    return None


def get_default_provider() -> str:
    """Return default LLM provider name."""
    return "qianfan"


def get_default_model() -> str:
    """Return default LLM model ID."""
    return "glm-5"


def validate_pi_config(provider: str, model: str, api_key: str) -> None:
    """
    Phase 1: No-op stub.

    Phase 4 (Config UI): Merge-insert credentials into ~/.pi/agent/auth.json.
    - Atomic write: temp file + rename
    - Permissions: 0o600
    - Always preserve other providers' keys (merge, never overwrite)
    """
    # Phase 1: do nothing
    pass
