"""User configuration management for eSim Tool Manager."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from esim_tool_manager.errors import ConfigError, ValidationError
from esim_tool_manager.validators import validate_safe_path

DEFAULT_ESIM_PATH = r"C:\FOSSEE\eSim"


def get_base_data_dir() -> Path:
    """Return the base local app data directory for esim-tool-manager."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "esim-tool-manager"


class ConfigManager:
    """Handles reading, writing, and validating user configuration."""

    def __init__(self, config_dir: Path | None = None):
        self.base_dir = (config_dir or get_base_data_dir()).resolve()
        self.config_path = self.base_dir / "config.json"
        self.cache_dir = self.base_dir / "cache"
        self.tools_dir = self.base_dir / "tools"
        self.state_dir = self.base_dir / "state"
        self.logs_dir = self.base_dir / "logs"

    def initialize_directories(self) -> None:
        """Create standard data, cache, state, and log directories."""
        for directory in [
            self.base_dir,
            self.cache_dir,
            self.tools_dir,
            self.state_dir,
            self.logs_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self.save_config(self.get_default_config())

    def get_default_config(self) -> dict[str, Any]:
        """Return the default configuration dictionary."""
        return {
            "version": "1.0",
            "esim_path": DEFAULT_ESIM_PATH,
            "offline_mode": False,
            "auto_rollback": True,
            "last_update_check": None,
            "paths": {
                "cache": str(self.cache_dir),
                "tools": str(self.tools_dir),
                "state": str(self.state_dir),
                "logs": str(self.logs_dir),
            },
        }

    def load_config(self) -> dict[str, Any]:
        """Load and return configuration from file, initializing if missing."""
        if not self.config_path.exists():
            default_cfg = self.get_default_config()
            self.save_config(default_cfg)
            return default_cfg

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Configuration file at '{self.config_path}' is corrupted: {exc}",
                fix_suggestion="Run 'esim-tool-manager init' to reset configuration or repair JSON.",
            ) from exc
        except OSError as exc:
            raise ConfigError(
                f"Cannot read configuration file: {exc}",
                fix_suggestion="Check file permissions for the config directory.",
            ) from exc

        if not isinstance(data, dict):
            raise ConfigError(
                f"Config at '{self.config_path}' is malformed (expected a JSON object).",
                fix_suggestion="Run 'esim-tool-manager init' to reinitialize.",
            )

        return data

    def save_config(self, config_data: dict[str, Any]) -> None:
        """Atomically write configuration to disk."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=str(self.base_dir), delete=False, encoding="utf-8"
            ) as tf:
                temp_file = tf.name
                json.dump(config_data, tf, indent=2)
            os.replace(temp_file, str(self.config_path))
        except OSError as exc:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            raise ConfigError(
                f"Failed to write configuration file: {exc}",
                fix_suggestion="Ensure write permissions exist for your user profile directory.",
            ) from exc

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by key."""
        config = self.load_config()
        return config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value, validating key and value constraints."""
        allowed_keys = {"esim_path", "offline_mode", "auto_rollback", "last_update_check"}
        if key not in allowed_keys:
            raise ValidationError(
                f"Configuration key '{key}' is not allowed. Valid keys are: {sorted(allowed_keys)}",
                fix_suggestion="Choose from: esim_path, offline_mode, auto_rollback.",
            )

        if key == "esim_path":
            # Must be a safe path string without traversal
            safe_p = validate_safe_path(str(value))
            value = str(safe_p)

        config = self.load_config()
        config[key] = value
        self.save_config(config)
