"""Unit tests for tool detector and version evaluation."""

from pathlib import Path
from unittest.mock import patch

from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.registry import ToolRegistry


def test_detect_tool_missing(mock_registry: ToolRegistry, mock_config_mgr) -> None:
    detector = ToolDetector(registry=mock_registry, config=mock_config_mgr)
    with patch.object(detector, "find_tool_binary", return_value=None):
        spec = mock_registry.get_tool("ngspice")
        status = detector.detect_tool(spec)
        assert status.status == "MISSING"
        assert status.binary_path is None
        assert "esim-tool-manager install" in (status.fix_suggestion or "")


def test_detect_tool_ok(mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path) -> None:
    detector = ToolDetector(registry=mock_registry, config=mock_config_mgr)
    fake_bin = tmp_path / "ngspice.exe"
    fake_bin.touch()

    with (
        patch.object(detector, "find_tool_binary", return_value=fake_bin),
        patch.object(detector, "query_tool_version", return_value="43.0"),
    ):
        spec = mock_registry.get_tool("ngspice")
        status = detector.detect_tool(spec)
        assert status.status == "OK"
        assert status.installed_version == "43.0"
        assert status.binary_path == str(fake_bin.resolve())


def test_detect_tool_outdated(mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path) -> None:
    detector = ToolDetector(registry=mock_registry, config=mock_config_mgr)
    fake_bin = tmp_path / "ngspice.exe"
    fake_bin.touch()

    with (
        patch.object(detector, "find_tool_binary", return_value=fake_bin),
        # min is 34.0, pinned is 43.0. Version 38.0 meets min, but is outdated
        patch.object(detector, "query_tool_version", return_value="38.0"),
    ):
        spec = mock_registry.get_tool("ngspice")
        status = detector.detect_tool(spec)
        assert status.status == "OUTDATED"
        assert status.installed_version == "38.0"
        assert "recommended pinned version is 43.0" in (status.fix_suggestion or "")


def test_detect_tool_incompatible(
    mock_registry: ToolRegistry, mock_config_mgr, tmp_path: Path
) -> None:
    detector = ToolDetector(registry=mock_registry, config=mock_config_mgr)
    fake_bin = tmp_path / "ngspice.exe"
    fake_bin.touch()

    with (
        patch.object(detector, "find_tool_binary", return_value=fake_bin),
        # min is 34.0. Version 26.0 is below min
        patch.object(detector, "query_tool_version", return_value="26.0"),
    ):
            spec = mock_registry.get_tool("ngspice")
            status = detector.detect_tool(spec)
            assert status.status == "INCOMPATIBLE"
            assert status.installed_version == "26.0"
            assert "below minimum requirement" in (status.fix_suggestion or "")
