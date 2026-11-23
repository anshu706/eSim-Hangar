"""Unit tests for M1 CLI commands (init, list, check, config, version)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from esim_tool_manager.cli import main
from esim_tool_manager.detector import ToolStatus


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["version"])
    assert code == 0
    captured = capsys.readouterr()
    assert "esim-tool-manager v0.1.0" in captured.out


def test_cli_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    code = main(["init"])
    assert code == 0
    assert (tmp_path / "esim-tool-manager" / "config.json").exists()


def test_cli_init_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    code = main(["--dry-run", "init"])
    assert code == 0
    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out
    assert not (tmp_path / "esim-tool-manager" / "config.json").exists()


def test_cli_list(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["list"])
    assert code == 0
    captured = capsys.readouterr()
    # Table must display python, git, ngspice, kicad
    for tool in ["Python", "Git", "Ngspice", "KiCad"]:
        assert tool in captured.out or tool.lower() in captured.out


def test_cli_check_returns_exit_code_2_on_missing(capsys: pytest.CaptureFixture[str]) -> None:
    # On a clean test environment where ngspice/kicad aren't installed yet, check must exit with 2
    mock_statuses = {
        "python": ToolStatus("python", "Python", "OK", "3.11.9", "3.10.0", "3.11.9", "C:/py.exe"),
        "git": ToolStatus("git", "Git", "OK", "2.40.0", "2.30.0", "2.40.0", "C:/git.exe"),
        "ngspice": ToolStatus(
            "ngspice", "Ngspice", "MISSING", None, "34.0", "43.0", None, "Install ngspice"
        ),
        "kicad": ToolStatus(
            "kicad", "KiCad", "MISSING", None, "7.0.0", "8.0.0", None, "Install kicad"
        ),
    }
    with patch("esim_tool_manager.detector.ToolDetector.detect_all", return_value=mock_statuses):
        code = main(["check"])
        assert code == 2
        captured = capsys.readouterr()
        assert "MISSING" in captured.out or "MISSING" in captured.err


def test_cli_config_set_and_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    code_init = main(["init"])
    assert code_init == 0

    code_set = main(["config", "set", "esim_path", str(tmp_path / "MyEsim")])
    assert code_set == 0

    code_get = main(["config", "get", "esim_path"])
    assert code_get == 0
    captured = capsys.readouterr()
    assert str(tmp_path / "MyEsim") in captured.out
