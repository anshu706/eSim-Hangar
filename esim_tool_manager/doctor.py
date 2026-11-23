"""System diagnostic health checks for eSim Tool Manager."""

import sys
from dataclasses import dataclass

import requests

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.deps import DependencyChecker
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.platform_win import (
    check_git_installed,
    check_winget_installed,
    is_windows,
)
from esim_tool_manager.registry import ToolRegistry


@dataclass
class DiagnosticCheck:
    """Represents the result of a single system health check."""

    name: str
    category: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    fix_suggestion: str | None = None


class SystemDoctor:
    """Performs deep environment, tool, network, permission, and configuration diagnostics."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        detector: ToolDetector | None = None,
        dep_checker: DependencyChecker | None = None,
        config_mgr: ConfigManager | None = None,
    ):
        self.config = config_mgr or ConfigManager()
        self.registry = registry or ToolRegistry()
        self.detector = detector or ToolDetector(registry=self.registry, config=self.config)
        self.dep_checker = dep_checker or DependencyChecker(
            registry=self.registry, detector=self.detector
        )

    def check_os_and_python(self) -> list[DiagnosticCheck]:
        """Check Operating System platform and Python runtime version."""
        checks: list[DiagnosticCheck] = []
        if is_windows():
            checks.append(
                DiagnosticCheck("Operating System", "System", "PASS", f"Windows ({sys.platform})")
            )
        else:
            checks.append(
                DiagnosticCheck(
                    "Operating System",
                    "System",
                    "WARN",
                    f"Non-Windows environment ({sys.platform}). Some Windows features will be simulated.",
                    "Run on Windows 10/11 for full native winget & registry integration.",
                )
            )

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append(
            DiagnosticCheck("Python Version", "System", "PASS", f"Python {py_ver} (>= 3.10)")
        )
        return checks

    def check_prerequisites(self) -> list[DiagnosticCheck]:
        """Verify Windows Package Manager (winget) and Git availability."""
        checks: list[DiagnosticCheck] = []
        try:
            winget_v = check_winget_installed()
            checks.append(
                DiagnosticCheck("winget Package Manager", "Prerequisites", "PASS", f"v{winget_v}")
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                DiagnosticCheck(
                    "winget Package Manager",
                    "Prerequisites",
                    "WARN",
                    f"winget unavailable: {exc}",
                    "Install or update 'App Installer' from the Microsoft Store.",
                )
            )

        try:
            git_v = check_git_installed()
            checks.append(DiagnosticCheck("Git VCS", "Prerequisites", "PASS", git_v))
        except Exception as exc:  # noqa: BLE001
            checks.append(
                DiagnosticCheck(
                    "Git VCS",
                    "Prerequisites",
                    "WARN",
                    f"Git unavailable: {exc}",
                    "Run 'esim-tool-manager install git' or install Git for Windows.",
                )
            )
        return checks

    def check_write_permissions(self) -> list[DiagnosticCheck]:
        """Test write permissions across all application data directories."""
        checks: list[DiagnosticCheck] = []
        for d in [
            self.config.base_dir,
            self.config.cache_dir,
            self.config.tools_dir,
            self.config.state_dir,
            self.config.logs_dir,
        ]:
            try:
                d.mkdir(parents=True, exist_ok=True)
                test_file = d / ".perm_check"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
                checks.append(
                    DiagnosticCheck(f"Directory Write ({d.name})", "Filesystem", "PASS", str(d))
                )
            except OSError as exc:
                checks.append(
                    DiagnosticCheck(
                        f"Directory Write ({d.name})",
                        "Filesystem",
                        "FAIL",
                        f"Permission denied: {exc}",
                        f"Verify folder permissions for {d}",
                    )
                )
        return checks

    def check_network(self) -> list[DiagnosticCheck]:
        """Check outbound network and HTTPS connectivity to allowed repositories."""
        checks: list[DiagnosticCheck] = []
        endpoints = [
            ("GitHub API / Releases", "https://github.com"),
            ("SourceForge Mirror", "https://downloads.sourceforge.net"),
        ]
        for name, url in endpoints:
            try:
                resp = requests.head(url, timeout=5, allow_redirects=True)
                if resp.status_code < 500:
                    checks.append(
                        DiagnosticCheck(
                            f"Network: {name}", "Network", "PASS", f"HTTP {resp.status_code}"
                        )
                    )
                else:
                    checks.append(
                        DiagnosticCheck(
                            f"Network: {name}",
                            "Network",
                            "WARN",
                            f"Server returned status {resp.status_code}",
                            "Check proxy or firewall settings.",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    DiagnosticCheck(
                        f"Network: {name}",
                        "Network",
                        "WARN",
                        f"Cannot reach endpoint: {exc}",
                        "Check internet connection. Note: cached tools will still work offline.",
                    )
                )
        return checks

    def check_log_file_health(self) -> list[DiagnosticCheck]:
        """Verify the health and size of the rotating action log file."""
        log_file = self.config.logs_dir / "actions.log"
        if not log_file.is_file():
            return [DiagnosticCheck("Action Log Health", "Logging", "PASS", "Log file initialized")]
        size_bytes = log_file.stat().st_size
        size_mb = round(size_bytes / (1024 * 1024), 2)
        if size_bytes <= 1024 * 1024 * 2:
            return [
                DiagnosticCheck(
                    "Action Log Health", "Logging", "PASS", f"Size: {size_mb} MB (healthy)"
                )
            ]
        return [
            DiagnosticCheck(
                "Action Log Health",
                "Logging",
                "WARN",
                f"Log file large: {size_mb} MB",
                "Rotating handler will rotate automatically when limit is reached.",
            )
        ]

    def run_all_checks(self) -> list[DiagnosticCheck]:
        """Execute full diagnostic battery and return consolidated results."""
        results: list[DiagnosticCheck] = []
        results.extend(self.check_os_and_python())
        results.extend(self.check_prerequisites())
        results.extend(self.check_write_permissions())
        results.extend(self.check_network())
        results.extend(self.check_log_file_health())

        # Tool statuses
        statuses = self.detector.detect_all()
        for name, st in sorted(statuses.items()):
            status_code = (
                "PASS" if st.status == "OK" else ("WARN" if st.status == "OUTDATED" else "FAIL")
            )
            results.append(
                DiagnosticCheck(
                    f"Tool: {st.display_name}",
                    "Tools",
                    status_code,
                    f"{st.status} (Version: {st.installed_version or 'None'}, Min: {st.required_version})",
                    st.fix_suggestion,
                )
            )

        # Dependencies
        dep_res = self.dep_checker.check_all_dependencies()
        for name, d in sorted(dep_res.items()):
            if not d.is_valid:
                results.append(
                    DiagnosticCheck(
                        f"Dependency: {name}",
                        "Dependencies",
                        "FAIL",
                        "; ".join(d.details),
                        f"Install missing dependencies for {name}.",
                    )
                )

        return results
