"""Unit tests for configuration manager."""

from pathlib import Path

import pytest

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.errors import ConfigError, ValidationError


def test_config_initialization(temp_dir: Path) -> None:
    mgr = ConfigManager(config_dir=temp_dir)
    mgr.initialize_directories()

    assert mgr.config_path.exists()
    assert mgr.cache_dir.exists()
    assert mgr.tools_dir.exists()
    assert mgr.state_dir.exists()
    assert mgr.logs_dir.exists()

    cfg = mgr.load_config()
    assert cfg["version"] == "1.0"
    assert "esim_path" in cfg


def test_config_get_and_set(mock_config_mgr: ConfigManager) -> None:
    mock_config_mgr.set("esim_path", r"D:\Tools\eSim")
    assert mock_config_mgr.get("esim_path") == str(Path(r"D:\Tools\eSim").resolve())

    mock_config_mgr.set("offline_mode", True)
    assert mock_config_mgr.get("offline_mode") is True


def test_config_set_disallowed_key(mock_config_mgr: ConfigManager) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        mock_config_mgr.set("forbidden_setting", "value")


def test_config_set_path_traversal(mock_config_mgr: ConfigManager) -> None:
    with pytest.raises(ValidationError, match="Path traversal detected"):
        mock_config_mgr.set("esim_path", r"C:\FOSSEE\..\..\Windows")


def test_config_corrupted_json(mock_config_mgr: ConfigManager) -> None:
    with open(mock_config_mgr.config_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json")

    with pytest.raises(ConfigError, match="corrupted"):
        mock_config_mgr.load_config()
