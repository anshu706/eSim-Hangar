"""Unit tests for tool registry parsing and validation."""

from pathlib import Path

import pytest
import yaml

from esim_tool_manager.errors import RegistryError, ValidationError
from esim_tool_manager.registry import ToolRegistry


def test_load_valid_registry(mock_registry: ToolRegistry) -> None:
    tools = mock_registry.get_all_tools()
    assert "ngspice" in tools
    assert "kicad" in tools
    assert "python" in tools
    assert "git" in tools

    ngspice = mock_registry.get_tool("ngspice")
    assert ngspice.name == "ngspice"
    assert ngspice.install.method == "direct_download"
    assert ngspice.install.sha256 is not None

    kicad = mock_registry.get_tool("kicad")
    assert kicad.install.method == "winget"
    assert kicad.install.package_id == "KiCad.KiCad"
    assert kicad.dependencies == ["python"]


def test_registry_unknown_tool(mock_registry: ToolRegistry) -> None:
    with pytest.raises(RegistryError, match="Unknown tool"):
        mock_registry.get_tool("nonexistent")


def test_registry_missing_file(temp_dir: Path) -> None:
    missing_path = temp_dir / "does_not_exist.yaml"
    with pytest.raises(RegistryError, match="not found"):
        ToolRegistry(yaml_path=missing_path)


def test_registry_malformed_yaml(temp_dir: Path) -> None:
    bad_yaml = temp_dir / "bad.yaml"
    bad_yaml.write_text("tools: [invalid format]", encoding="utf-8")
    with pytest.raises(RegistryError, match="expected top-level 'tools' mapping"):
        ToolRegistry(yaml_path=bad_yaml)


def test_registry_insecure_direct_download(temp_dir: Path) -> None:
    insecure_data = {
        "version": "1.0",
        "tools": {
            "badtool": {
                "name": "badtool",
                "binary": "badtool.exe",
                "minimum_version": "1.0",
                "pinned_version": "1.0",
                "install": {
                    "method": "direct_download",
                    "url": "http://insecure-domain.org/tool.zip",
                    "sha256": "fc3d4d418499c9b807f0f3032c55537d628d03d86c3f2a742735487497ecb5c0",
                },
            }
        },
    }
    insecure_yaml = temp_dir / "insecure.yaml"
    with open(insecure_yaml, "w", encoding="utf-8") as f:
        yaml.dump(insecure_data, f)

    with pytest.raises(ValidationError, match="Insecure URL scheme"):
        ToolRegistry(yaml_path=insecure_yaml)
