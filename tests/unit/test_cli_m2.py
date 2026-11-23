"""Unit tests for M2 CLI install command."""

from unittest.mock import patch

import pytest

from esim_tool_manager.cli import main


def test_cli_install_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--dry-run", "install", "ngspice"])
    assert code == 0
    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out


def test_cli_install_cancelled(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("builtins.input", return_value="n"):
        code = main(["install", "ngspice"])
        assert code == 3
        captured = capsys.readouterr()
        assert "cancelled" in captured.out.lower() or "cancelled" in captured.err.lower()


def test_cli_install_yes_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "esim_tool_manager.installer.ToolInstaller.install_tool",
        return_value=(True, "Successfully installed Ngspice"),
    ):
        code = main(["install", "ngspice", "--yes"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Successfully installed Ngspice" in captured.out


def test_cli_install_all_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--dry-run", "install", "all"])
    assert code == 0
    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out
