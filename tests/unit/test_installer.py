"""Unit tests for tool installer."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from esim_tool_manager.detector import ToolStatus
from esim_tool_manager.errors import DependencyError
from esim_tool_manager.installer import ToolInstaller
from esim_tool_manager.registry import ToolRegistry


def test_installer_idempotent_when_already_ok(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    installer = ToolInstaller(registry=mock_registry, config_mgr=mock_config_mgr)

    mock_ok_status = ToolStatus(
        name="python",
        display_name="Python",
        status="OK",
        installed_version="3.11.9",
        required_version="3.10.0",
        pinned_version="3.11.9",
        binary_path="C:/Python/python.exe",
    )
    with patch.object(installer.detector, "detect_tool", return_value=mock_ok_status):
        ok, msg = installer.install_tool("python")
        assert ok is True
        assert "already installed and up to date" in msg


def test_installer_dry_run(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    installer = ToolInstaller(registry=mock_registry, config_mgr=mock_config_mgr)
    mock_missing = ToolStatus(
        name="ngspice",
        display_name="Ngspice",
        status="MISSING",
        installed_version=None,
        required_version="34.0",
        pinned_version="43.0",
        binary_path=None,
    )
    with patch.object(installer.detector, "detect_tool", return_value=mock_missing):
        ok, msg = installer.install_tool("ngspice", dry_run=True)
        assert ok is True
        assert "[DRY RUN]" in msg


def test_installer_winget_execution(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    installer = ToolInstaller(registry=mock_registry, config_mgr=mock_config_mgr)

    initial_missing = ToolStatus(
        name="git",
        display_name="Git",
        status="MISSING",
        installed_version=None,
        required_version="2.30.0",
        pinned_version="2.56.1",
        binary_path=None,
    )
    after_ok = ToolStatus(
        name="git",
        display_name="Git",
        status="OK",
        installed_version="2.56.1",
        required_version="2.30.0",
        pinned_version="2.56.1",
        binary_path="C:/Program Files/Git/cmd/git.exe",
    )

    fake_proc = subprocess.CompletedProcess(
        args=["winget", "install"], returncode=0, stdout="Installed", stderr=""
    )

    with (
        patch.object(installer.detector, "detect_tool", side_effect=[initial_missing, after_ok]),
        patch("esim_tool_manager.installer.check_winget_installed", return_value="v1.29"),
        patch("esim_tool_manager.installer.run_command_safe", return_value=fake_proc) as mock_run,
    ):
        ok, msg = installer.install_tool("git")
        assert ok is True
        assert "Successfully installed Git" in msg
        mock_run.assert_called_once()
        cmd_called = mock_run.call_args[0][0]
        assert "Git.Git" in cmd_called


def test_installer_direct_download(
    mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path
) -> None:
    installer = ToolInstaller(registry=mock_registry, config_mgr=mock_config_mgr)

    initial_missing = ToolStatus(
        name="ngspice",
        display_name="Ngspice",
        status="MISSING",
        installed_version=None,
        required_version="34.0",
        pinned_version="43.0",
        binary_path=None,
    )
    after_ok = ToolStatus(
        name="ngspice",
        display_name="Ngspice",
        status="OK",
        installed_version="43.0",
        required_version="34.0",
        pinned_version="43.0",
        binary_path=str(tmp_path / "ngspice.exe"),
    )

    fake_archive = tmp_path / "ngspice.zip"
    fake_archive.touch()

    with (
        patch.object(installer.detector, "detect_tool", side_effect=[initial_missing, after_ok]),
        patch.object(installer.downloader, "download", return_value=fake_archive),
        patch.object(installer, "extract_archive", return_value=tmp_path),
    ):
        ok, msg = installer.install_tool("ngspice")
        assert ok is True
        assert "Successfully installed Ngspice" in msg
        # State record must be recorded
        rec = installer.state_mgr.get_record("ngspice")
        assert rec is not None
        assert rec.version == "43.0"


def test_installer_unmet_dependencies_raises_error(
    mock_registry: ToolRegistry, mock_config_mgr
) -> None:
    installer = ToolInstaller(registry=mock_registry, config_mgr=mock_config_mgr)
    # kicad depends on python
    with (
        patch.object(
            installer.dep_checker,
            "check_tool_dependencies",
            return_value=MagicMock(is_valid=False, details=["Python is MISSING"]),
        ),
        pytest.raises(DependencyError, match="prerequisites are unmet"),
    ):
        installer.install_tool("kicad")
