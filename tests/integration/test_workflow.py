"""Integration tests running full multi-step workflows against simulated environments."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from esim_tool_manager.cli import main
from esim_tool_manager.detector import ToolStatus


def test_integration_workflow_init_list_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Workflow 1: Fresh machine initialization -> list status -> dependency check."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    # Step 1: Init
    assert main(["init"]) == 0
    assert (tmp_path / "esim-tool-manager" / "config.json").exists()

    # Step 2: List
    assert main(["list"]) == 0
    list_out = capsys.readouterr().out
    assert "Python" in list_out
    assert "Ngspice" in list_out

    # Step 3: Check
    # Missing tools should return exit code 2
    code_check = main(["check"])
    assert code_check == 2


def test_integration_workflow_install_configure_revert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Workflow 2: Direct download tool install -> configure PATH & eSim INI -> revert undo."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert main(["init"]) == 0
    assert main(["config", "set", "esim_path", str(tmp_path / "eSim")]) == 0

    fake_archive = tmp_path / "ngspice.7z"
    fake_archive.write_bytes(b"dummy")

    fake_ngspice_bin = tmp_path / "esim-tool-manager" / "tools" / "Spice64" / "bin" / "ngspice.exe"
    fake_ngspice_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_ngspice_bin.touch()

    # Mock detection before and after install
    missing_status = ToolStatus("ngspice", "Ngspice", "MISSING", None, "34.0", "43.0", None)
    installed_status = ToolStatus(
        "ngspice", "Ngspice", "OK", "43.0", "34.0", "43.0", str(fake_ngspice_bin)
    )

    installed_flag = {"installed": False}

    def mock_detect(spec: Any) -> ToolStatus:
        if spec.name == "ngspice":
            if installed_flag["installed"]:
                return installed_status
            installed_flag["installed"] = True
            return missing_status
        return ToolStatus(
            spec.name,
            spec.display_name,
            "OK",
            spec.pinned_version,
            spec.minimum_version,
            spec.pinned_version,
            f"C:/tools/{spec.binary}",
        )

    with (
        patch("esim_tool_manager.installer.Downloader.download", return_value=fake_archive),
        patch("esim_tool_manager.installer.ToolInstaller.extract_archive"),
        patch(
            "esim_tool_manager.detector.ToolDetector.detect_tool",
            side_effect=mock_detect,
        ),
        patch("esim_tool_manager.configurator.get_user_path", return_value=["C:/Windows"]),
        patch("esim_tool_manager.configurator.set_user_path") as mock_set_path,
    ):
        # 1. Install tool
        res_inst = main(["install", "ngspice", "--yes"])
        assert res_inst == 0

        # 2. Configure system
        res_cfg = main(["configure", "--yes"])
        assert res_cfg == 0
        mock_set_path.assert_called()

        # 3. Revert system
        res_rev = main(["configure", "--revert", "--yes"])
        assert res_rev == 0


def test_integration_workflow_update_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Workflow 3: Tool version update simulation followed by rollback restoration."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert main(["init"]) == 0
    assert main(["config", "set", "esim_path", str(tmp_path / "eSim")]) == 0

    # Seed state with existing version 42.0
    state_file = tmp_path / "esim-tool-manager" / "state" / "ngspice.json"
    state_file.write_text(
        json.dumps(
            {
                "tool_name": "ngspice",
                "version": "43.0",
                "install_method": "direct_download",
                "install_path": "C:/Spice64",
                "installed_at": "2026-01-01T00:00:00Z",
                "previous_version": "42.0",
                "previous_path": "C:/Spice64_v42",
                "previous_method": "direct_download",
            }
        ),
        encoding="utf-8",
    )

    # Roll back to 42.0
    res_rb = main(["rollback", "ngspice"])
    assert res_rb == 0
    out = capsys.readouterr().out
    assert "rolled back" in out.lower()
    assert "42.0" in out
