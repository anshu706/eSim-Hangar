"""Detection and version inspection of external tools."""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.registry import ToolRegistry, ToolSpec


@dataclass
class ToolStatus:
    """Status evaluation of a managed tool."""

    name: str
    display_name: str
    status: str  # "OK", "OUTDATED", "MISSING", "INCOMPATIBLE"
    installed_version: str | None
    required_version: str  # minimum_version
    pinned_version: str
    binary_path: str | None
    fix_suggestion: str | None = None


class ToolDetector:
    """Finds tool binaries, executes version commands, and evaluates compatibility."""

    def __init__(self, registry: ToolRegistry | None = None, config: ConfigManager | None = None):
        self.registry = registry or ToolRegistry()
        self.config = config or ConfigManager()

    def find_tool_binary(self, spec: ToolSpec) -> Path | None:
        """Search PATH, user tools directory, and standard default installation paths."""
        # 1. If tool is python and matches current runtime
        if spec.name == "python":
            py_path = shutil.which("python.exe") or shutil.which("python") or sys.executable
            if py_path and Path(py_path).is_file():
                return Path(py_path).resolve()

        # 2. Check system PATH
        found_in_path = shutil.which(spec.binary)
        if found_in_path and Path(found_in_path).is_file():
            return Path(found_in_path).resolve()

        # 3. Check inside local tool directory (%LOCALAPPDATA%\esim-tool-manager\tools\...)
        cfg = self.config.load_config()
        tools_base = Path(cfg.get("paths", {}).get("tools", self.config.tools_dir))

        candidates = [
            tools_base / spec.name / "bin" / spec.binary,
            tools_base / spec.name / spec.binary,
            tools_base / "Spice64" / "bin" / spec.binary,
            tools_base / "Spice64" / spec.binary,
        ]

        # 4. Check known Windows default locations
        if spec.name == "ngspice":
            candidates.extend(
                [
                    Path(r"C:\Spice64\bin\ngspice.exe"),
                    Path(r"C:\Spice64\ngspice.exe"),
                    Path(r"C:\Program Files\Spice64\bin\ngspice.exe"),
                ]
            )
        elif spec.name == "kicad":
            # Search common KiCad version directories (7.0, 8.0, 9.0, 10.0)
            for v in ["10.0", "9.0", "8.0", "7.0"]:
                candidates.extend(
                    [
                        Path(rf"C:\Program Files\KiCad\{v}\bin\kicad-cli.exe"),
                        Path(rf"C:\Program Files\KiCad\{v}\bin\kicad.exe"),
                    ]
                )
            candidates.append(Path(r"C:\Program Files\KiCad\bin\kicad.exe"))
        elif spec.name == "git":
            candidates.extend(
                [
                    Path(r"C:\Program Files\Git\bin\git.exe"),
                    Path(r"C:\Program Files\Git\cmd\git.exe"),
                ]
            )

        for cand in candidates:
            if cand.is_file():
                return cand.resolve()

        return None

    def query_tool_version(self, spec: ToolSpec, binary_path: Path) -> str | None:
        """Execute the tool's version command and extract its semantic version."""
        cmd = list(spec.version_command)
        # Substitute the actual binary path for the first command token
        cmd[0] = str(binary_path)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            raw_output = (proc.stdout + " " + proc.stderr).strip()
            if not raw_output:
                return None

            match = re.search(spec.version_pattern, raw_output, re.IGNORECASE)
            if match:
                # Capture the first non-empty group
                for group in match.groups():
                    if group and group[0].isdigit():
                        return group
                return match.group(1) if match.groups() else match.group(0)

            # Fallback general semantic version pattern
            fallback = re.search(r"(\d+(\.\d+)+)", raw_output)
            if fallback:
                return fallback.group(1)

        except (subprocess.SubprocessError, OSError):
            return None

        return None

    def detect_tool(self, spec: ToolSpec) -> ToolStatus:
        """Detect binary, extract version, and compute status."""
        binary = self.find_tool_binary(spec)
        if not binary:
            return ToolStatus(
                name=spec.name,
                display_name=spec.display_name,
                status="MISSING",
                installed_version=None,
                required_version=spec.minimum_version,
                pinned_version=spec.pinned_version,
                binary_path=None,
                fix_suggestion=f"Install {spec.display_name} using: esim-tool-manager install {spec.name}",
            )

        installed_ver_str = self.query_tool_version(spec, binary)
        if not installed_ver_str:
            # Binary exists but version cannot be probed
            return ToolStatus(
                name=spec.name,
                display_name=spec.display_name,
                status="INCOMPATIBLE",
                installed_version=None,
                required_version=spec.minimum_version,
                pinned_version=spec.pinned_version,
                binary_path=str(binary),
                fix_suggestion=f"Verify {spec.display_name} installation at {binary} or reinstall.",
            )

        try:
            inst_v = Version(installed_ver_str)
            min_v = Version(spec.minimum_version)
            pin_v = Version(spec.pinned_version)

            if inst_v < min_v:
                status = "INCOMPATIBLE"
                fix = (
                    f"Version {installed_ver_str} is below minimum requirement {spec.minimum_version}. "
                    f"Run 'esim-tool-manager update {spec.name}' or upgrade manually."
                )
            elif inst_v < pin_v:
                status = "OUTDATED"
                fix = (
                    f"Version {installed_ver_str} meets minimum ({spec.minimum_version}), but "
                    f"recommended pinned version is {spec.pinned_version}. "
                    f"Run 'esim-tool-manager update {spec.name}' to upgrade."
                )
            else:
                status = "OK"
                fix = None

        except InvalidVersion:
            status = "OK"
            fix = None

        return ToolStatus(
            name=spec.name,
            display_name=spec.display_name,
            status=status,
            installed_version=installed_ver_str,
            required_version=spec.minimum_version,
            pinned_version=spec.pinned_version,
            binary_path=str(binary),
            fix_suggestion=fix,
        )

    def detect_all(self) -> dict[str, ToolStatus]:
        """Detect and evaluate all registered tools."""
        statuses: dict[str, ToolStatus] = {}
        for name, spec in self.registry.get_all_tools().items():
            statuses[name] = self.detect_tool(spec)
        return statuses
