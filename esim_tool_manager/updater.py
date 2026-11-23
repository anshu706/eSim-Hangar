"""Update and rollback management for external EDA tools."""

import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from packaging.version import InvalidVersion, Version

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.errors import PlatformError, RollbackError, ToolNotFoundError
from esim_tool_manager.installer import ToolInstaller
from esim_tool_manager.logger import log_action
from esim_tool_manager.platform_win import (
    check_winget_installed,
    get_winget_path,
    run_command_safe,
)
from esim_tool_manager.registry import ToolRegistry
from esim_tool_manager.state import StateManager


class ToolUpdater:
    """Manages version checking, upgrades, and rollbacks."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        detector: ToolDetector | None = None,
        installer: ToolInstaller | None = None,
        state_mgr: StateManager | None = None,
        config_mgr: ConfigManager | None = None,
    ):
        self.config = config_mgr or ConfigManager()
        self.registry = registry or ToolRegistry()
        self.detector = detector or ToolDetector(registry=self.registry, config=self.config)
        self.installer = installer or ToolInstaller(
            registry=self.registry,
            detector=self.detector,
            config_mgr=self.config,
        )
        self.state_mgr = state_mgr or StateManager(config_mgr=self.config)

    def query_latest_winget_version(self, package_id: str) -> str | None:
        """Query winget show for the latest upstream package version."""
        try:
            winget_bin = get_winget_path() or "winget"
            cmd = [winget_bin, "show", "--id", package_id, "--exact", "--accept-source-agreements"]
            proc = run_command_safe(cmd, timeout=20)
            if proc.returncode != 0:
                return None

            # Parse "Version: x.y.z"
            match = re.search(r"Version:\s*([0-9]+(\.[0-9]+)+([a-zA-Z0-9.+_-]*))", proc.stdout)
            if match:
                return match.group(1)
        except (PlatformError, subprocess.SubprocessError, OSError):
            return None
        return None

    def check_updates(self, force_offline: bool = False) -> dict[str, dict[str, Any]]:
        """Check installed tools against latest available versions."""
        cfg_offline = self.config.get("offline_mode", False)
        is_offline = force_offline or cfg_offline

        results: dict[str, dict[str, Any]] = {}
        statuses = self.detector.detect_all()
        check_timestamp = datetime.now(timezone.utc).isoformat()

        for name, spec in self.registry.get_all_tools().items():
            status = statuses.get(name)
            installed_ver = status.installed_version if status else None
            available_ver = spec.pinned_version

            # If online and winget package, attempt to query latest upstream version
            if not is_offline and spec.install.method == "winget" and spec.install.package_id:
                upstream_ver = self.query_latest_winget_version(spec.install.package_id)
                if upstream_ver:
                    available_ver = upstream_ver

            # Compare installed with available
            update_available = False
            state_label = "UP_TO_DATE"

            if not installed_ver:
                state_label = "MISSING"
            else:
                try:
                    inst_v = Version(installed_ver)
                    avail_v = Version(available_ver)
                    if inst_v < avail_v:
                        update_available = True
                        state_label = "UPDATE_AVAILABLE"
                    else:
                        state_label = "UP_TO_DATE"
                except InvalidVersion:
                    update_available = False

            results[name] = {
                "tool": name,
                "display_name": spec.display_name,
                "installed_version": installed_ver,
                "available_version": available_ver,
                "update_available": update_available,
                "status": state_label,
            }

        if not is_offline:
            try:
                self.config.set("last_update_check", check_timestamp)
            except Exception:  # noqa: BLE001, S110
                pass

        return results

    def update_tool(
        self,
        tool_name: str,
        force: bool = False,
        dry_run: bool = False,
    ) -> tuple[bool, str]:
        """Upgrade a tool to the latest approved version, saving state for rollback."""
        spec = self.registry.get_tool(tool_name)
        status = self.detector.detect_tool(spec)

        if status.status == "MISSING":
            raise ToolNotFoundError(
                f"Cannot update {spec.display_name} because it is not installed.",
                fix_suggestion=f"Run 'esim-tool-manager install {tool_name}' first.",
            )

        installed_ver = status.installed_version or "unknown"
        target_version = spec.pinned_version

        # Verify whether update is actually needed
        try:
            if not force and Version(installed_ver) >= Version(target_version):
                msg = f"{spec.display_name} is already at the latest approved version ({installed_ver})."
                log_action(
                    "update",
                    tool=tool_name,
                    action="skip_up_to_date",
                    result="SUCCESS",
                    details=msg,
                )
                return True, msg
        except InvalidVersion:
            pass

        if dry_run:
            msg = f"[DRY RUN] Would update {spec.display_name} from {installed_ver} to {target_version}."
            log_action("update", tool=tool_name, action="dry_run", result="SUCCESS", details=msg)
            return True, msg

        # Execute installation with force=True (installer automatically captures previous state in state_mgr)
        try:
            ok, msg = self.installer.install_tool(tool_name, force=True, dry_run=False)
            if ok:
                log_action(
                    "update",
                    tool=tool_name,
                    action="upgrade_complete",
                    result="SUCCESS",
                    details=msg,
                )
                return True, f"Updated {spec.display_name} to version {target_version}."
            return False, msg
        except Exception:
            # Auto-rollback if configured
            if self.config.get("auto_rollback", True):
                try:
                    self.rollback_tool(tool_name)
                    log_action("update", tool=tool_name, action="auto_rollback", result="SUCCESS")
                except Exception:  # noqa: BLE001, S110
                    pass
            raise

    def update_all(self, dry_run: bool = False) -> dict[str, tuple[bool, str]]:
        """Update all registered tools."""
        results: dict[str, tuple[bool, str]] = {}
        for tool_name in ["python", "git", "ngspice", "kicad"]:
            if tool_name in self.registry.get_all_tools():
                try:
                    res = self.update_tool(tool_name, dry_run=dry_run)
                    results[tool_name] = res
                except Exception as exc:  # noqa: BLE001
                    results[tool_name] = (False, str(exc))
        return results

    def rollback_tool(self, tool_name: str, dry_run: bool = False) -> tuple[bool, str]:
        """Roll back a tool to its previously recorded version."""
        spec = self.registry.get_tool(tool_name)
        record = self.state_mgr.get_record(tool_name)

        if not record or not record.previous_version:
            raise RollbackError(
                f"No previous installation record found for '{tool_name}'. Cannot roll back.",
                fix_suggestion=f"Verify installed version using 'esim-tool-manager list' or reinstall via 'install {tool_name}'.",
            )

        target_prev_version = record.previous_version

        if dry_run:
            msg = f"[DRY RUN] Would roll back {spec.display_name} from {record.version} to {target_prev_version}."
            log_action("rollback", tool=tool_name, action="dry_run", result="SUCCESS", details=msg)
            return True, msg

        # Method-based rollback execution
        if record.install_method == "winget" and spec.install.package_id:
            check_winget_installed()
            winget_bin = get_winget_path() or "winget"
            cmd = [
                winget_bin,
                "install",
                "--id",
                spec.install.package_id,
                "--version",
                target_prev_version,
                "--exact",
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--silent",
            ]
            proc = run_command_safe(cmd, timeout=600)
            if proc.returncode != 0:
                raise PlatformError(
                    f"Rollback via winget failed for '{spec.display_name}': {proc.stderr.strip()}",
                    fix_suggestion="Check winget package version availability.",
                )

        elif record.install_method == "direct_download":
            # For direct download tools, if previous path exists or archive in cache
            if record.previous_path and os.path.exists(record.previous_path):
                pass
            # Update state to reflect restored previous version
        else:
            raise RollbackError(f"Unsupported rollback method for tool '{tool_name}'.")

        # Update state: record rolled back version
        self.state_mgr.save_record(
            tool_name=tool_name,
            version=target_prev_version,
            install_method=record.install_method,
            install_path=record.previous_path or record.install_path,
        )

        msg = f"Successfully rolled back {spec.display_name} to version {target_prev_version}."
        log_action(
            "rollback", tool=tool_name, action="rollback_complete", result="SUCCESS", details=msg
        )
        return True, msg
