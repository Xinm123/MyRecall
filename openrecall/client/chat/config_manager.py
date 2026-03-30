"""
Config manager for Pi agent integration.

Handles reading/writing Pi configuration:
  - ~/.pi/agent/auth.json: API keys for providers
  - Atomic write with 0o600 permissions
  - Merge-preserve other providers' keys
"""

import json
import os
import stat
from pathlib import Path
from typing import Optional


PI_CONFIG_DIR = Path.home() / ".pi" / "agent"
AUTH_JSON = PI_CONFIG_DIR / "auth.json"
MYRECALL_CONFIG = PI_CONFIG_DIR / "myrecall-config.json"  # User's provider/model choice

# Supported providers for UI
SUPPORTED_PROVIDERS = [
    {
        "id": "qianfan",
        "name": "Baidu Qianfan",
        "url": "https://console.bce.baidu.com/qianfan/",
        "api_base": "https://aip.baidubce.com",
        "models": [
            {"id": "deepseek-v3.2", "name": "DeepSeek V3.2"},
            {"id": "kimi-k2.5", "name": "Kimi K2.5"},
            {"id": "glm-5", "name": "GLM-5"},
            {"id": "minimax-m2.5", "name": "MiniMax M2.5"},
        ]
    },
    {
        "id": "kimi-coding",
        "name": "Kimi (免费)",
        "url": "https://platform.moonshot.cn/",
        "api_base": "https://api.moonshot.cn",
        "models": [
            {"id": "moonshot-v1-8k", "name": "Moonshot V1 (8K)"},
            {"id": "moonshot-v1-32k", "name": "Moonshot V1 (32K)"},
            {"id": "moonshot-v1-128k", "name": "Moonshot V1 (128K)"},
        ]
    },
    {
        "id": "minimax-cn",
        "name": "MiniMax (China)",
        "url": "https://platform.minimaxi.com/",
        "api_base": "https://api.minimaxi.com",
        "models": [
            {"id": "MiniMax-M2.7", "name": "MiniMax M2.7"},
            {"id": "MiniMax-M2.5", "name": "MiniMax M2.5"},
            {"id": "MiniMax-M2.1", "name": "MiniMax M2.1"},
        ]
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "url": "https://console.anthropic.com/",
        "api_base": "https://api.anthropic.com",
        "models": [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
        ]
    },
    {
        "id": "custom",
        "name": "Local GLM (Thinking)",
        "url": "",
        "api_base": "",  # loaded from OPENRECALL_CHAT_API_BASE or ~/.pi/agent/auth.json
        "models": [
            {"id": "glm-4.5-flash", "name": "GLM-4.5-Flash (Thinking)"},
        ]
    },
]

# Provider name → environment variable name mapping
PROVIDER_ENV_MAP: dict[str, str] = {
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "kimi-coding": "KIMI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "qianfan": "QIANFAN_API_KEY",
    "custom": "CUSTOM_API_KEY",
}


def get_chat_api_base() -> str:
    """
    Get custom chat API base URL.

    Priority:
      1. Environment variable OPENRECALL_CHAT_API_BASE
      2. ~/.pi/agent/auth.json custom.api_base
      3. "" (empty, uses provider default)
    """
    if env_val := os.environ.get("OPENRECALL_CHAT_API_BASE"):
        return env_val.strip()

    if AUTH_JSON.exists():
        try:
            auth_data = json.loads(AUTH_JSON.read_text())
            custom_data = auth_data.get("custom", {})
            api_base = custom_data.get("api_base")
            if api_base:
                return str(api_base).strip()
        except (json.JSONDecodeError, OSError):
            pass

    return ""


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


def get_provider_info(provider_id: str) -> Optional[dict]:
    """Get provider info by ID."""
    for p in SUPPORTED_PROVIDERS:
        if p["id"] == provider_id:
            return p
    return None


def save_api_key(provider: str, api_key: str, api_base: Optional[str] = None) -> None:
    """
    Save API key for a provider to ~/.pi/agent/auth.json.

    - Creates directory if needed
    - Merges with existing auth data (preserves other providers)
    - Atomic write: temp file + rename
    - Sets permissions to 0o600
    - Also saves provider as user's current choice

    For 'custom' provider, api_base is also saved.
    """
    # Ensure directory exists
    PI_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Read existing auth data
    auth_data: dict = {}
    if AUTH_JSON.exists():
        try:
            auth_data = json.loads(AUTH_JSON.read_text())
        except (json.JSONDecodeError, OSError):
            auth_data = {}

    # Merge the provider key
    provider_entry: dict = {"type": "api_key", "key": api_key}
    if provider == "custom" and api_base:
        provider_entry["api_base"] = api_base
    auth_data[provider] = provider_entry

    # Atomic write: temp file + rename
    temp_path = AUTH_JSON.with_suffix(".tmp")
    temp_path.write_text(json.dumps(auth_data, indent=2))

    # Set permissions before rename
    temp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    temp_path.rename(AUTH_JSON)

    # Save provider as user's current choice
    save_user_choice(provider)


def save_user_choice(provider: str, model: Optional[str] = None) -> None:
    """Save user's provider and model choice to myrecall-config.json."""
    PI_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config_data: dict = {}
    if MYRECALL_CONFIG.exists():
        try:
            config_data = json.loads(MYRECALL_CONFIG.read_text())
        except (json.JSONDecodeError, OSError):
            config_data = {}

    config_data["provider"] = provider
    if model:
        config_data["model"] = model
    elif "model" in config_data:
        # Clear model if provider changed and no new model specified
        del config_data["model"]
    MYRECALL_CONFIG.write_text(json.dumps(config_data, indent=2))


def get_user_provider() -> str:
    """Get user's chosen provider, or default if not set."""
    if MYRECALL_CONFIG.exists():
        try:
            config_data = json.loads(MYRECALL_CONFIG.read_text())
            provider = config_data.get("provider")
            if provider and any(p["id"] == provider for p in SUPPORTED_PROVIDERS):
                return provider
        except (json.JSONDecodeError, OSError):
            pass
    return get_default_provider()


def get_default_model_for_provider(provider: str) -> str:
    """Get the first/default model for a provider."""
    provider_info = get_provider_info(provider)
    if provider_info and provider_info.get("models"):
        return provider_info["models"][0]["id"]
    return get_default_model()


def get_user_model() -> str:
    """Get the model for user's chosen provider."""
    provider = get_user_provider()
    provider_info = get_provider_info(provider)

    # Check if user has a saved model preference
    if MYRECALL_CONFIG.exists():
        try:
            config_data = json.loads(MYRECALL_CONFIG.read_text())
            saved_model = config_data.get("model")
            if saved_model and provider_info:
                # Verify model is valid for this provider
                for m in provider_info.get("models", []):
                    if m["id"] == saved_model:
                        return saved_model
        except (json.JSONDecodeError, OSError):
            pass

    # Return first model for provider
    return get_default_model_for_provider(provider)


def get_current_config() -> dict:
    """
    Get current LLM configuration for UI.

    Returns provider, model, and whether API key is configured for each provider.
    """
    # Get user's chosen provider and model
    provider = get_user_provider()
    model = get_user_model()

    # Check if API key is configured for this provider
    api_key = get_api_key(provider)

    # Check which providers have API keys configured
    provider_keys = {}
    for p in SUPPORTED_PROVIDERS:
        provider_keys[p["id"]] = get_api_key(p["id"]) is not None

    # Build supported_providers with dynamic api_base for custom
    supported_providers = []
    for p in SUPPORTED_PROVIDERS:
        p_copy = dict(p)
        if p["id"] == "custom":
            p_copy["api_base"] = get_chat_api_base()
        supported_providers.append(p_copy)

    return {
        "provider": provider,
        "model": model,
        "has_api_key": api_key is not None,
        "provider_keys": provider_keys,
        "supported_providers": supported_providers,
    }
