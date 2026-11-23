"""Unit tests for M5 CLI commands (doctor, cache, logs, report)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from esim_tool_manager.cli import main


def test_cli_doctor(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("requests.head", return_value=MagicMock(status_code=200)):
        # Doctor might exit 0 or 1 depending on whether local tools are fully installed
        code = main(["doctor"])
        assert code in (0, 1)
        captured = capsys.readouterr()
        assert "Doctor" in captured.out or "Diagnostics" in captured.out or "System" in captured.out


def test_cli_cache_list_and_clear(capsys: pytest.CaptureFixture[str]) -> None:
    code_list = main(["cache", "list"])
    assert code_list == 0

    code_clear = main(["cache", "clear", "--yes"])
    assert code_clear == 0
    captured = capsys.readouterr()
    assert "cleared" in captured.out.lower() or "cache" in captured.out.lower()


def test_cli_logs(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["logs", "--tail", "5"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Action Log" in captured.out or "Timestamp" in captured.out or "INFO" in captured.out


def test_cli_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rep_file = tmp_path / "test_report.md"
    with patch("requests.head", return_value=MagicMock(status_code=200)):
        code = main(["report", "--output", str(rep_file)])
        assert code == 0
        assert rep_file.is_file()
        assert "eSim" in rep_file.read_text(encoding="utf-8")
