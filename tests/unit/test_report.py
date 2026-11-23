"""Unit tests for report generator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from esim_tool_manager.registry import ToolRegistry
from esim_tool_manager.report import ReportGenerator


def test_report_generator_markdown_content(
    mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path
) -> None:
    report_gen = ReportGenerator(registry=mock_registry, config_mgr=mock_config_mgr)
    with patch("requests.head", return_value=MagicMock(status_code=200)):
        md = report_gen.generate_markdown()
        assert "# eSim Automated Tool Manager" in md
        assert "## 1. Executive Summary" in md
        assert "## 2. Managed Tools Compliance Status" in md
        assert "## 3. System Health & Doctor Diagnostics" in md
        assert "## 4. User Environment & Registry PATH (HKCU)" in md
        assert "## 5. Recent Action Logs" in md

        out_path = tmp_path / "custom_report.md"
        saved = report_gen.write_report(out_path)
        assert saved.is_file()
        saved_text = saved.read_text(encoding="utf-8")
        assert "# eSim Automated Tool Manager" in saved_text
        assert "## 1. Executive Summary" in saved_text
        assert "## 2. Managed Tools Compliance Status" in saved_text
