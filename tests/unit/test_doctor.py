"""Unit tests for SystemDoctor diagnostics."""

from unittest.mock import MagicMock, patch

from esim_tool_manager.doctor import SystemDoctor
from esim_tool_manager.registry import ToolRegistry


def test_doctor_checks(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    doctor = SystemDoctor(registry=mock_registry, config_mgr=mock_config_mgr)

    with (
        patch("requests.head", return_value=MagicMock(status_code=200)),
        patch("esim_tool_manager.doctor.check_winget_installed", return_value="v1.29"),
        patch("esim_tool_manager.doctor.check_git_installed", return_value="git version 2.40"),
    ):
        checks = doctor.run_all_checks()
        assert len(checks) > 5

        categories = {c.category for c in checks}
        assert "System" in categories
        assert "Prerequisites" in categories
        assert "Filesystem" in categories
        assert "Network" in categories
        assert "Tools" in categories


def test_doctor_detects_write_permission_failure(
    mock_registry: ToolRegistry, mock_config_mgr
) -> None:
    doctor = SystemDoctor(registry=mock_registry, config_mgr=mock_config_mgr)
    with patch("pathlib.Path.mkdir", side_effect=PermissionError("Mock Permission Denied")):
        checks = doctor.check_write_permissions()
        assert any(c.status == "FAIL" for c in checks)
