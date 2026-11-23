"""Unit tests for tool updater and rollback system."""

from unittest.mock import patch

import pytest

from esim_tool_manager.detector import ToolStatus
from esim_tool_manager.errors import RollbackError, ToolNotFoundError
from esim_tool_manager.registry import ToolRegistry
from esim_tool_manager.updater import ToolUpdater


def test_updater_check_updates_offline(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    updater = ToolUpdater(registry=mock_registry, config_mgr=mock_config_mgr)

    mock_statuses = {
        "python": ToolStatus("python", "Python", "OK", "3.11.9", "3.10.0", "3.11.9", "C:/py.exe"),
        "git": ToolStatus("git", "Git", "OUTDATED", "2.35.0", "2.30.0", "2.56.1", "C:/git.exe"),
        "ngspice": ToolStatus(
            "ngspice", "Ngspice", "MISSING", None, "34.0", "43.0", None, "Install ngspice"
        ),
        "kicad": ToolStatus(
            "kicad", "KiCad", "MISSING", None, "7.0.0", "10.0.8", None, "Install kicad"
        ),
    }
    with patch.object(updater.detector, "detect_all", return_value=mock_statuses):
        res = updater.check_updates(force_offline=True)
        assert res["python"]["status"] == "UP_TO_DATE"
        assert res["git"]["status"] == "UPDATE_AVAILABLE"
        assert res["git"]["update_available"] is True
        assert res["ngspice"]["status"] == "MISSING"


def test_updater_update_already_up_to_date(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    updater = ToolUpdater(registry=mock_registry, config_mgr=mock_config_mgr)
    mock_status = ToolStatus("python", "Python", "OK", "3.11.9", "3.10.0", "3.11.9", "C:/py.exe")

    with patch.object(updater.detector, "detect_tool", return_value=mock_status):
        ok, msg = updater.update_tool("python")
        assert ok is True
        assert "already at the latest" in msg


def test_updater_update_dry_run(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    updater = ToolUpdater(registry=mock_registry, config_mgr=mock_config_mgr)
    mock_status = ToolStatus("git", "Git", "OUTDATED", "2.35.0", "2.30.0", "2.56.1", "C:/git.exe")

    with patch.object(updater.detector, "detect_tool", return_value=mock_status):
        ok, msg = updater.update_tool("git", dry_run=True)
        assert ok is True
        assert "[DRY RUN]" in msg


def test_updater_update_missing_tool_raises_error(
    mock_registry: ToolRegistry, mock_config_mgr
) -> None:
    updater = ToolUpdater(registry=mock_registry, config_mgr=mock_config_mgr)
    mock_status = ToolStatus("ngspice", "Ngspice", "MISSING", None, "34.0", "43.0", None, "Install")

    with (
        patch.object(updater.detector, "detect_tool", return_value=mock_status),
        pytest.raises(ToolNotFoundError, match="is not installed"),
    ):
        updater.update_tool("ngspice")


def test_updater_rollback_no_previous_record(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    updater = ToolUpdater(registry=mock_registry, config_mgr=mock_config_mgr)
    with pytest.raises(RollbackError, match="No previous installation record"):
        updater.rollback_tool("ngspice")


def test_updater_rollback_success(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    updater = ToolUpdater(registry=mock_registry, config_mgr=mock_config_mgr)
    # Save a record that has a previous version
    updater.state_mgr.save_record("ngspice", "42.0", "direct_download", "C:/Spice64")
    updater.state_mgr.save_record("ngspice", "43.0", "direct_download", "C:/Spice64")

    ok, msg = updater.rollback_tool("ngspice")
    assert ok is True
    assert "Successfully rolled back Ngspice to version 42.0" in msg

    # State should now be updated to 42.0
    rec = updater.state_mgr.get_record("ngspice")
    assert rec is not None
    assert rec.version == "42.0"
