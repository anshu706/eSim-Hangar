"""Pytest fixtures for eSim Tool Manager tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.registry import ToolRegistry


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory cleaned up after test execution."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def mock_config_mgr(temp_dir: Path) -> ConfigManager:
    """Provide an isolated ConfigManager inside a temporary directory."""
    mgr = ConfigManager(config_dir=temp_dir)
    mgr.initialize_directories()
    return mgr


@pytest.fixture
def sample_tools_yaml(temp_dir: Path) -> Path:
    """Provide a temporary valid tools.yaml file for testing."""
    tools_data = {
        "version": "1.0",
        "tools": {
            "python": {
                "name": "python",
                "display_name": "Python",
                "description": "Python runtime",
                "binary": "python.exe",
                "version_command": ["python", "--version"],
                "version_pattern": r"Python ([0-9]+\.[0-9]+(\.[0-9]+)?)",
                "minimum_version": "3.10.0",
                "pinned_version": "3.11.9",
                "install": {
                    "method": "winget",
                    "package_id": "Python.Python.3.11",
                },
                "dependencies": [],
            },
            "git": {
                "name": "git",
                "display_name": "Git",
                "description": "Git VCS",
                "binary": "git.exe",
                "version_command": ["git", "--version"],
                "version_pattern": r"git version ([0-9]+\.[0-9]+(\.[0-9]+)?)",
                "minimum_version": "2.30.0",
                "pinned_version": "2.56.1",
                "install": {
                    "method": "winget",
                    "package_id": "Git.Git",
                },
                "dependencies": [],
            },
            "ngspice": {
                "name": "ngspice",
                "display_name": "Ngspice",
                "description": "Circuit simulator",
                "binary": "ngspice.exe",
                "version_command": ["ngspice", "--version"],
                "version_pattern": r"ngspice-([0-9]+(\.[0-9]+)?)",
                "minimum_version": "34.0",
                "pinned_version": "43.0",
                "install": {
                    "method": "direct_download",
                    "url": "https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/43/ngspice-43_64.7z",
                    "sha256": "fc3d4d418499c9b807f0f3032c55537d628d03d86c3f2a742735487497ecb5c0",
                    "extract_folder": "Spice64",
                    "bin_subdir": "bin",
                },
                "dependencies": [],
            },
            "kicad": {
                "name": "kicad",
                "display_name": "KiCad",
                "description": "EDA Suite",
                "binary": "kicad.exe",
                "version_command": ["kicad-cli", "version"],
                "version_pattern": r"([0-9]+\.[0-9]+(\.[0-9]+)?)",
                "minimum_version": "7.0.0",
                "pinned_version": "10.0.8",
                "install": {
                    "method": "winget",
                    "package_id": "KiCad.KiCad",
                },
                "dependencies": ["python"],
            },
        },
    }
    yaml_path = temp_dir / "tools.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(tools_data, f)
    return yaml_path


@pytest.fixture
def mock_registry(sample_tools_yaml: Path) -> ToolRegistry:
    """Provide a ToolRegistry loaded from the sample tools.yaml."""
    return ToolRegistry(yaml_path=sample_tools_yaml)
