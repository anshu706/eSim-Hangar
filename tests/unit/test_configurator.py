"""Unit tests for configuration handler, PATH manipulation, and revert."""

from pathlib import Path
from unittest.mock import patch

import pytest

from esim_tool_manager.configurator import ToolConfigurator
from esim_tool_manager.detector import ToolStatus
from esim_tool_manager.errors import ConfigError
from esim_tool_manager.registry import ToolRegistry


def test_configurator_generate_config_and_preview(
    mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path
) -> None:
    configurator = ToolConfigurator(registry=mock_registry, config_mgr=mock_config_mgr)
    fake_py = tmp_path / "python.exe"
    fake_py.touch()
    fake_git = tmp_path / "git.exe"
    fake_git.touch()
    fake_ngspice = tmp_path / "ngspice.exe"
    fake_ngspice.touch()
    fake_kicad = tmp_path / "kicad.exe"
    fake_kicad.touch()

    mock_statuses = {
        "python": ToolStatus("python", "Python", "OK", "3.11.9", "3.10.0", "3.11.9", str(fake_py)),
        "git": ToolStatus("git", "Git", "OK", "2.40.0", "2.30.0", "2.40.0", str(fake_git)),
        "ngspice": ToolStatus(
            "ngspice", "Ngspice", "OK", "43.0", "34.0", "43.0", str(fake_ngspice)
        ),
        "kicad": ToolStatus("kicad", "KiCad", "OK", "8.0.0", "7.0.0", "8.0.0", str(fake_kicad)),
    }

    with (
        patch.object(configurator.detector, "detect_all", return_value=mock_statuses),
        patch(
            "esim_tool_manager.configurator.get_user_path",
            return_value=["C:/Windows", "C:/Windows/System32"],
        ),
    ):
        preview = configurator.preview_configure()
        assert len(preview["added_path_entries"]) > 0
        assert "esim_config.ini" in preview["target_esim_cfg"]
        assert "cfg_diff" in preview
        assert "[eSim]" in preview["new_cfg_content"]
        assert f"ngspice_path = {fake_ngspice}" in preview["new_cfg_content"]


def test_configurator_apply_and_revert(
    mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path
) -> None:
    configurator = ToolConfigurator(registry=mock_registry, config_mgr=mock_config_mgr)
    esim_cfg_file = tmp_path / "esim_config.ini"
    fake_py = tmp_path / "python.exe"
    fake_py.touch()

    mock_statuses = {
        "python": ToolStatus("python", "Python", "OK", "3.11.9", "3.10.0", "3.11.9", str(fake_py)),
    }

    with (
        patch.object(configurator, "get_esim_config_path", return_value=esim_cfg_file),
        patch.object(configurator.detector, "detect_all", return_value=mock_statuses),
        patch("esim_tool_manager.configurator.get_user_path", return_value=["C:/Windows"]),
        patch("esim_tool_manager.configurator.set_user_path") as mock_set_path,
    ):
        # 1. Apply configuration
        ok, msg = configurator.apply_configure()
        assert ok is True
        assert "Configuration successfully applied" in msg
        mock_set_path.assert_called_once()
        assert esim_cfg_file.is_file()
        assert configurator.record_file.is_file()

        # 2. Revert configuration
        ok_rev, msg_rev = configurator.apply_revert()
        assert ok_rev is True
        assert "reverted to original state" in msg_rev
        assert not configurator.record_file.exists()


def test_configurator_revert_without_record_raises_error(
    mock_registry: ToolRegistry, mock_config_mgr
) -> None:
    configurator = ToolConfigurator(registry=mock_registry, config_mgr=mock_config_mgr)
    with pytest.raises(ConfigError, match="No configuration change record found"):
        configurator.apply_revert()
