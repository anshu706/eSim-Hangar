"""Unit tests for tool dependency evaluation."""

from esim_tool_manager.deps import DependencyChecker
from esim_tool_manager.detector import ToolStatus
from esim_tool_manager.registry import ToolRegistry


def test_dependency_checker_all_satisfied(mock_registry: ToolRegistry) -> None:
    checker = DependencyChecker(registry=mock_registry)
    mock_statuses = {
        "python": ToolStatus(
            name="python",
            display_name="Python",
            status="OK",
            installed_version="3.11.9",
            required_version="3.10.0",
            pinned_version="3.11.9",
            binary_path="C:/Python/python.exe",
        ),
        "kicad": ToolStatus(
            name="kicad",
            display_name="KiCad",
            status="OK",
            installed_version="8.0.0",
            required_version="7.0.0",
            pinned_version="8.0.0",
            binary_path="C:/KiCad/kicad.exe",
        ),
    }

    res = checker.check_tool_dependencies("kicad", cached_statuses=mock_statuses)
    assert res.is_valid is True
    assert len(res.missing_dependencies) == 0
    assert len(res.incompatible_dependencies) == 0


def test_dependency_checker_missing_dep(mock_registry: ToolRegistry) -> None:
    checker = DependencyChecker(registry=mock_registry)
    mock_statuses = {
        "python": ToolStatus(
            name="python",
            display_name="Python",
            status="MISSING",
            installed_version=None,
            required_version="3.10.0",
            pinned_version="3.11.9",
            binary_path=None,
        ),
        "kicad": ToolStatus(
            name="kicad",
            display_name="KiCad",
            status="OK",
            installed_version="8.0.0",
            required_version="7.0.0",
            pinned_version="8.0.0",
            binary_path="C:/KiCad/kicad.exe",
        ),
    }

    res = checker.check_tool_dependencies("kicad", cached_statuses=mock_statuses)
    assert res.is_valid is False
    assert "python" in res.missing_dependencies
    assert any("MISSING" in d for d in res.details)


def test_dependency_checker_incompatible_dep(mock_registry: ToolRegistry) -> None:
    checker = DependencyChecker(registry=mock_registry)
    mock_statuses = {
        "python": ToolStatus(
            name="python",
            display_name="Python",
            status="INCOMPATIBLE",
            installed_version="3.8.0",
            required_version="3.10.0",
            pinned_version="3.11.9",
            binary_path="C:/Python/python.exe",
        ),
        "kicad": ToolStatus(
            name="kicad",
            display_name="KiCad",
            status="OK",
            installed_version="8.0.0",
            required_version="7.0.0",
            pinned_version="8.0.0",
            binary_path="C:/KiCad/kicad.exe",
        ),
    }

    res = checker.check_tool_dependencies("kicad", cached_statuses=mock_statuses)
    assert res.is_valid is False
    assert "python" in res.incompatible_dependencies
    assert any("INCOMPATIBLE" in d for d in res.details)
