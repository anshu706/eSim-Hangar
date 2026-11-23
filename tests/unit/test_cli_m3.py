"""Unit tests for M3 CLI update and rollback commands."""

from unittest.mock import patch

import pytest

from esim_tool_manager.cli import main


def test_cli_update_check(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["update", "check"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Tool" in captured.out or "Python" in captured.out


def test_cli_update_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "esim_tool_manager.updater.ToolUpdater.update_tool",
        return_value=(True, "[DRY RUN] Would update"),
    ):
        code = main(["update", "git", "--dry-run"])
        assert code == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out


def test_cli_update_yes_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "esim_tool_manager.updater.ToolUpdater.update_tool",
        return_value=(True, "Updated Ngspice to version 43.0."),
    ):
        code = main(["update", "ngspice", "--yes"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Updated Ngspice" in captured.out


def test_cli_rollback_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "esim_tool_manager.updater.ToolUpdater.rollback_tool",
        return_value=(True, "[DRY RUN] Would roll back"),
    ):
        code = main(["rollback", "ngspice", "--dry-run"])
        assert code == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out


def test_cli_rollback_no_record(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["rollback", "ngspice"])
    assert code == 1
    captured = capsys.readouterr()
    assert "No previous" in captured.out or "No previous" in captured.err
