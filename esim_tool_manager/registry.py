"""Registry parser and tool definitions for eSim Tool Manager."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from esim_tool_manager.errors import RegistryError
from esim_tool_manager.validators import (
    validate_download_url,
    validate_sha256,
    validate_tool_name,
    validate_version_string,
)


@dataclass
class InstallSpec:
    """Specification for tool installation on Windows."""

    method: str  # "winget" or "direct_download"
    package_id: str | None = None
    url: str | None = None
    sha256: str | None = None
    extract_folder: str | None = None
    bin_subdir: str | None = None
    fallback_url: str | None = None


@dataclass
class ToolSpec:
    """Specification of an external tool managed by eSim Tool Manager."""

    name: str
    display_name: str
    description: str
    binary: str
    version_command: list[str]
    version_pattern: str
    minimum_version: str
    pinned_version: str
    install: InstallSpec
    dependencies: list[str] = field(default_factory=list)


class ToolRegistry:
    """Loads, validates, and indexes tool specifications from tools.yaml."""

    def __init__(self, yaml_path: Path | None = None):
        self.yaml_path = yaml_path or self.find_default_tools_yaml()
        self._tools: dict[str, ToolSpec] = {}
        self.load()

    @staticmethod
    def find_default_tools_yaml() -> Path:
        """Locate tools.yaml in cwd or relative to the package directory."""
        candidates = [
            Path.cwd() / "tools.yaml",
            Path(__file__).resolve().parent.parent / "tools.yaml",
            Path(__file__).resolve().parent / "tools.yaml",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise RegistryError(
            "Could not locate 'tools.yaml'.",
            fix_suggestion="Ensure 'tools.yaml' exists in the working directory or project root.",
        )

    def load(self) -> None:
        """Parse tools.yaml and validate all entries."""
        if not self.yaml_path.exists():
            raise RegistryError(
                f"Tools registry file not found: {self.yaml_path}",
                fix_suggestion="Ensure 'tools.yaml' is present in the application directory.",
            )

        try:
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise RegistryError(
                f"Malformed tools.yaml syntax: {exc}",
                fix_suggestion="Check YAML syntax and indentation in tools.yaml.",
            ) from exc

        if not isinstance(data, dict) or "tools" not in data or not isinstance(data["tools"], dict):
            raise RegistryError(
                "Invalid tools.yaml structure: expected top-level 'tools' mapping.",
                fix_suggestion="Format tools.yaml with a top-level 'tools:' dictionary.",
            )

        parsed_tools: dict[str, ToolSpec] = {}
        for raw_name, raw_spec in data["tools"].items():
            tool_name = validate_tool_name(str(raw_name))
            if not isinstance(raw_spec, dict):
                raise RegistryError(f"Tool specification for '{tool_name}' must be a mapping.")

            display_name = str(raw_spec.get("display_name", tool_name.capitalize()))
            description = str(raw_spec.get("description", ""))
            binary = str(raw_spec.get("binary", ""))
            if not binary:
                raise RegistryError(f"Tool '{tool_name}' is missing required 'binary' field.")

            version_cmd = raw_spec.get("version_command", [binary, "--version"])
            if not isinstance(version_cmd, list) or not all(
                isinstance(c, str) for c in version_cmd
            ):
                raise RegistryError(f"version_command for '{tool_name}' must be a list of strings.")

            version_pattern = str(raw_spec.get("version_pattern", r"([0-9]+\.[0-9]+(\.[0-9]+)?)"))
            min_ver = validate_version_string(str(raw_spec.get("minimum_version", "1.0")))
            pinned_ver = validate_version_string(str(raw_spec.get("pinned_version", min_ver)))

            # Validate install block
            raw_install = raw_spec.get("install", {})
            if not isinstance(raw_install, dict):
                raise RegistryError(f"Tool '{tool_name}' install section must be a mapping.")

            win_install = raw_install.get("windows", raw_install)
            method = str(win_install.get("method", "winget"))
            package_id = win_install.get("package_id")
            url = win_install.get("url")
            sha256 = win_install.get("sha256")
            extract_folder = win_install.get("extract_folder")
            bin_subdir = win_install.get("bin_subdir")
            fallback_url = win_install.get("fallback_url")

            if method == "winget":
                if not package_id:
                    raise RegistryError(
                        f"Tool '{tool_name}' with winget method requires 'package_id'."
                    )
            elif method == "direct_download":
                if not url:
                    raise RegistryError(
                        f"Tool '{tool_name}' direct_download method requires 'url'."
                    )
                validate_download_url(url)
                if not sha256:
                    raise RegistryError(
                        f"Tool '{tool_name}' direct_download method requires 'sha256'."
                    )
                sha256 = validate_sha256(sha256)
            else:
                raise RegistryError(
                    f"Tool '{tool_name}' has unsupported install method '{method}'."
                )

            if fallback_url:
                validate_download_url(fallback_url)

            deps = raw_spec.get("dependencies", [])
            if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
                raise RegistryError(f"Dependencies for '{tool_name}' must be a list of tool names.")
            for d in deps:
                validate_tool_name(d)

            spec = ToolSpec(
                name=tool_name,
                display_name=display_name,
                description=description,
                binary=binary,
                version_command=version_cmd,
                version_pattern=version_pattern,
                minimum_version=min_ver,
                pinned_version=pinned_ver,
                install=InstallSpec(
                    method=method,
                    package_id=package_id,
                    url=url,
                    sha256=sha256,
                    extract_folder=extract_folder,
                    bin_subdir=bin_subdir,
                    fallback_url=fallback_url,
                ),
                dependencies=deps,
            )
            parsed_tools[tool_name] = spec

        self._tools = parsed_tools

    def get_tool(self, name: str) -> ToolSpec:
        """Get specification for a single tool by name."""
        validate_tool_name(name)
        if name not in self._tools:
            raise RegistryError(
                f"Unknown tool '{name}'. Available tools: {list(self._tools.keys())}",
                fix_suggestion="Use 'esim-tool-manager list' to see supported tools.",
            )
        return self._tools[name]

    def get_all_tools(self) -> dict[str, ToolSpec]:
        """Return mapping of all registered tools."""
        return dict(self._tools)
