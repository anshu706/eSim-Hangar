"""Unit tests for M4 CLI configure and revert commands."""

from unittest.mock import patch

import pytest

from esim_tool_manager.cli import main


def test_cli_configure_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["configure", "--dry-run"])
    assert code == 0
    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out or "Target eSim configuration" in captured.out


def test_cli_configure_yes_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch(
            "esim_tool_manager.configurator.ToolConfigurator.apply_configure",
            return_value=(True, "Config applied"),
        ),
        patch(
            "esim_tool_manager.configurator.ToolConfigurator.preview_configure",
            return_value={
                "added_path_entries": [],
                "target_esim_cfg": "C:/eSim/cfg.ini",
                "cfg_diff": "",
            },
        ),
    ):
        code = main(["configure", "--yes"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Config applied" in captured.out


def test_cli_configure_revert_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    fake_preview = {
        "added_entries_to_remove": ["C:/Tools/bin"],
        "esim_config_path": "C:/eSim/cfg.ini",
        "cfg_diff": "",
    }
    with (
        patch(
            "esim_tool_manager.configurator.ToolConfigurator.preview_revert",
            return_value=fake_preview,
        ),
        patch(
            "esim_tool_manager.configurator.ToolConfigurator.apply_revert",
            return_value=(True, "[DRY RUN] Would remove"),
        ),
    ):
        code = main(["configure", "--revert", "--dry-run"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Revert Preview" in captured.out


def test_cli_configure_revert_no_record(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["configure", "--revert"])
    assert code == 1
    captured = capsys.readouterr()
    assert (
        "No configuration change record" in captured.out
        or "No configuration change record" in captured.err
    )
