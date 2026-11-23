"""Installation engine for winget packages and direct HTTPS archives."""

import shutil
import zipfile
from pathlib import Path

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.deps import DependencyChecker
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.downloader import Downloader
from esim_tool_manager.errors import (
    DependencyError,
    EsimToolManagerError,
    IncompatibleVersionError,
    PlatformError,
    ToolNotFoundError,
)
from esim_tool_manager.logger import log_action
from esim_tool_manager.platform_win import (
    check_winget_installed,
    get_winget_path,
    is_admin,
    run_command_safe,
)
from esim_tool_manager.registry import ToolRegistry
from esim_tool_manager.state import StateManager


class ToolInstaller:
    """Manages installation of external EDA tools via winget or direct verified downloads."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        detector: ToolDetector | None = None,
        downloader: Downloader | None = None,
        state_mgr: StateManager | None = None,
        config_mgr: ConfigManager | None = None,
    ):
        self.config = config_mgr or ConfigManager()
        self.registry = registry or ToolRegistry()
        self.detector = detector or ToolDetector(registry=self.registry, config=self.config)
        self.downloader = downloader or Downloader(config_mgr=self.config)
        self.state_mgr = state_mgr or StateManager(config_mgr=self.config)
        self.dep_checker = DependencyChecker(registry=self.registry, detector=self.detector)

    def extract_archive(self, archive_path: Path, target_dir: Path) -> Path:
        """Extract a .zip or .7z archive safely into target_dir."""
        target_dir.mkdir(parents=True, exist_ok=True)
        archive_name = archive_path.name.lower()

        if archive_name.endswith(".zip"):
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(target_dir)
                return target_dir
            except zipfile.BadZipFile as exc:
                raise EsimToolManagerError(
                    f"Corrupted zip archive at '{archive_path}': {exc}",
                    fix_suggestion="Clear cache and re-download installer.",
                ) from exc

        # For .7z or tar archives, use Windows native tar.exe (bsdtar)
        tar_bin = shutil.which("tar.exe") or shutil.which("tar")
        if not tar_bin:
            raise PlatformError(
                "Windows tar.exe is not available for unpacking .7z archive.",
                fix_suggestion="Ensure tar.exe exists in Windows\\System32 or install 7-Zip.",
            )

        cmd = [tar_bin, "-xf", str(archive_path), "-C", str(target_dir)]
        proc = run_command_safe(cmd, timeout=300)
        if proc.returncode != 0:
            raise EsimToolManagerError(
                f"Failed to extract archive '{archive_path}': {proc.stderr.strip()}",
                fix_suggestion="Verify disk space and permissions in tools directory.",
            )
        return target_dir

    def install_tool(
        self,
        tool_name: str,
        force: bool = False,
        dry_run: bool = False,
    ) -> tuple[bool, str]:
        """Install a tool by name if missing or outdated. Idempotent when already compliant."""
        spec = self.registry.get_tool(tool_name)

        # 1. Dependency check
        dep_res = self.dep_checker.check_tool_dependencies(tool_name)
        if not dep_res.is_valid:
            err_msg = (
                f"Cannot install '{tool_name}' because prerequisites are unmet:\n"
                + "\n".join(dep_res.details)
            )
            raise DependencyError(err_msg, fix_suggestion="Install the missing dependencies first.")

        # 2. Idempotency Check
        current_status = self.detector.detect_tool(spec)
        if current_status.status == "OK" and not force:
            msg = f"{spec.display_name} is already installed and up to date (version {current_status.installed_version})."
            log_action(
                "install", tool=tool_name, action="skip_installed", result="SUCCESS", details=msg
            )
            return True, msg

        if dry_run:
            msg = (
                f"[DRY RUN] Would install {spec.display_name} (pinned version {spec.pinned_version}) "
                f"using method '{spec.install.method}'."
            )
            log_action("install", tool=tool_name, action="dry_run", result="SUCCESS", details=msg)
            return True, msg

        # 3. Method-based installation
        method = spec.install.method
        install_path: str | None = None

        if method == "winget":
            check_winget_installed()
            winget_bin = get_winget_path() or "winget"
            pkg_id = spec.install.package_id
            if not pkg_id:
                raise EsimToolManagerError(
                    f"No package_id specified for winget tool '{tool_name}'."
                )

            # Check admin rights notification
            if not is_admin():
                # Normal user: Winget will prompt for UAC if elevation is required
                pass

            cmd = [
                winget_bin,
                "install",
                "--id",
                pkg_id,
                "--exact",
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--silent",
            ]
            proc = run_command_safe(cmd, timeout=600)
            if proc.returncode != 0:
                raise PlatformError(
                    f"winget installation failed for '{spec.display_name}' (exit code {proc.returncode}):\n{proc.stderr.strip() or proc.stdout.strip()}",
                    fix_suggestion=f"Try running 'winget install --id {pkg_id}' directly in an elevated terminal.",
                )

        elif method == "direct_download":
            if not spec.install.url or not spec.install.sha256:
                raise EsimToolManagerError(f"Tool '{tool_name}' missing download URL or SHA256.")

            # Download archive with SHA-256 verification and resume
            archive_file = self.downloader.download(
                url=spec.install.url,
                expected_sha256=spec.install.sha256,
            )

            # Extract into tools directory
            tools_base = self.config.tools_dir
            extract_folder = spec.install.extract_folder or spec.name
            target_extract_dir = tools_base / extract_folder

            self.extract_archive(archive_file, target_extract_dir)
            install_path = str(target_extract_dir.resolve())

        else:
            raise EsimToolManagerError(f"Unsupported install method '{method}' for '{tool_name}'.")

        # 4. Post-installation verification
        new_status = self.detector.detect_tool(spec)
        if new_status.status == "MISSING":
            raise ToolNotFoundError(
                f"{spec.display_name} installation completed, but binary '{spec.binary}' was not found.",
                fix_suggestion="Check installation directory or run 'esim-tool-manager configure' to register PATH.",
            )

        if new_status.status == "INCOMPATIBLE":
            raise IncompatibleVersionError(
                f"{spec.display_name} was installed, but detected version {new_status.installed_version} "
                f"does not meet minimum required version {spec.minimum_version}.",
                fix_suggestion="Update tools.yaml or install a newer version.",
            )

        # 5. Record installation state for rollback
        self.state_mgr.save_record(
            tool_name=tool_name,
            version=new_status.installed_version or spec.pinned_version,
            install_method=method,
            install_path=install_path or new_status.binary_path,
        )

        success_msg = (
            f"Successfully installed {spec.display_name} (version {new_status.installed_version})."
        )
        log_action(
            "install",
            tool=tool_name,
            action="install_complete",
            result="SUCCESS",
            details=success_msg,
        )
        return True, success_msg

    def install_all(self, dry_run: bool = False) -> dict[str, tuple[bool, str]]:
        """Install all registered tools in dependency order."""
        results: dict[str, tuple[bool, str]] = {}
        # Order: python, git, ngspice, kicad
        ordered_tools = ["python", "git", "ngspice", "kicad"]
        all_specs = self.registry.get_all_tools()
        for t in all_specs:
            if t not in ordered_tools:
                ordered_tools.append(t)

        for tool_name in ordered_tools:
            if tool_name in all_specs:
                try:
                    res = self.install_tool(tool_name, dry_run=dry_run)
                    results[tool_name] = res
                except EsimToolManagerError as exc:
                    results[tool_name] = (False, exc.message)

        return results
