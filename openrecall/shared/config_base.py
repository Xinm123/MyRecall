"""Base class for TOML-based configuration."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Self

logger = logging.getLogger(__name__)


class TOMLConfig:
    """Base class for TOML-based configuration with fallback to defaults."""

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def from_toml(cls, path: str | Path | None = None) -> Self:
        """Load config from TOML file with fallback to defaults."""
        config_path = cls._find_config_path(path)
        if config_path and config_path.exists():
            try:
                import tomllib

                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                flat_data = cls._flatten_dict(data)
                return cls._from_dict(flat_data)
            except Exception as e:
                logger.warning(
                    f"Failed to load config from {config_path}: {e}, using defaults"
                )
                return cls._from_dict({})
        return cls._from_dict({})

    @classmethod
    def _find_config_path(cls, path: str | Path | None) -> Path | None:
        """Search for config file in standard locations."""
        if path:
            p = Path(path)
            if p.exists():
                return p
            return None

        if env_path := os.environ.get("OPENRECALL_CONFIG_PATH"):
            p = Path(env_path)
            if p.exists():
                return p
            return None

        if (project_path := Path.cwd() / cls._default_filename()).exists():
            return project_path

        if (home_path := Path.home() / ".myrecall" / cls._default_filename()).exists():
            return home_path

        return None

    @classmethod
    def _flatten_dict(cls, d: dict, parent_key: str = "", sep: str = ".") -> dict:
        """Flatten nested dict: {"server": {"port": 8083}} -> {"server.port": 8083}"""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(cls._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    @classmethod
    def _default_filename(cls) -> str:
        raise NotImplementedError

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        raise NotImplementedError
