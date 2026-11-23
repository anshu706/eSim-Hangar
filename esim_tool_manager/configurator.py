"""Configuration handling for HKCU user PATH and eSim tool configuration."""

import configparser
import difflib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.errors import ConfigError
from esim_tool_manager.logger import log_action
from esim_tool_manager.platform_win import (
    get_user_path,
    set_user_path,
)
from esim_tool_manager.registry import ToolRegistry


class ToolConfigurator:
    """Configures user-level PATH entries in HKCU and eSim configuration files."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        detector: ToolDetector | None = None,
        config_mgr: ConfigManager | None = None,
    ):
        self.config = config_mgr or ConfigManager()
        self.registry = registry or ToolRegistry()
        self.detector = detector or ToolDetector(registry=self.registry, config=self.config)
        self.record_file = self.config.state_dir / "config_record.json"

    def get_esim_config_path(self) -> Path:
        """Resolve the target path for eSim tool configuration file."""
        esim_base_str = self.config.get("esim_path", r"C:\FOSSEE\eSim")
        esim_base = Path(esim_base_str)
        # If the target eSim directory does not exist or isn't writable, write inside tool data dir
        if not esim_base.exists():
            try:
                esim_base.mkdir(parents=True, exist_ok=True)
            except OSError:
                esim_base = self.config.base_dir
        return esim_base / "esim_config.ini"

    def compute_managed_bin_dirs(self) -> list[str]:
        """Compute the list of directories that need to be in PATH for managed tools."""
        statuses = self.detector.detect_all()
        bin_dirs: list[str] = []

        for name, st in statuses.items():
            if st.binary_path and os.path.exists(st.binary_path):
                p = Path(st.binary_path).resolve()
                parent_dir = str(p.parent)
                if parent_dir not in bin_dirs:
                    bin_dirs.append(parent_dir)
            else:
                # Check default installation directory inside local tools folder
                spec = self.registry.get_tool(name)
                tools_base = self.config.tools_dir
                folder = spec.install.extract_folder or spec.name
                cand_dir = tools_base / folder / (spec.install.bin_subdir or "")
                if cand_dir.exists():
                    resolved_cand = str(cand_dir.resolve())
                    if resolved_cand not in bin_dirs:
                        bin_dirs.append(resolved_cand)

        return bin_dirs

    def generate_esim_config_content(self) -> str:
        """Generate content for eSim configuration file."""
        statuses = self.detector.detect_all()
        cp = configparser.ConfigParser()
        cp["eSim"] = {
            "configured_at": datetime.now(timezone.utc).isoformat(),
            "esim_path": str(self.config.get("esim_path", r"C:\FOSSEE\eSim")),
        }
        cp["Tools"] = {}
        for name, st in statuses.items():
            path_val = st.binary_path or "NOT_FOUND"
            cp["Tools"][f"{name}_path"] = path_val
            cp["Tools"][f"{name}_version"] = st.installed_version or "unknown"

        buf = io.StringIO()
        cp.write(buf)
        return buf.getvalue()

    def preview_configure(self) -> dict[str, Any]:
        """Preview changes to HKCU PATH and eSim configuration file without applying them."""
        current_path_entries = get_user_path()
        managed_dirs = self.compute_managed_bin_dirs()

        added_entries: list[str] = []
        for d in managed_dirs:
            norm_d = str(Path(d))
            if not any(str(Path(existing)) == norm_d for existing in current_path_entries):
                added_entries.append(norm_d)

        target_esim_cfg = self.get_esim_config_path()
        old_cfg_content = ""
        if target_esim_cfg.is_file():
            try:
                old_cfg_content = target_esim_cfg.read_text(encoding="utf-8")
            except OSError:
                old_cfg_content = ""

        new_cfg_content = self.generate_esim_config_content()

        diff_lines = list(
            difflib.unified_diff(
                old_cfg_content.splitlines(keepends=True),
                new_cfg_content.splitlines(keepends=True),
                fromfile="esim_config.ini (current)",
                tofile="esim_config.ini (new)",
            )
        )

        return {
            "current_path_entries": current_path_entries,
            "added_path_entries": added_entries,
            "target_esim_cfg": str(target_esim_cfg),
            "old_cfg_content": old_cfg_content,
            "new_cfg_content": new_cfg_content,
            "cfg_diff": "".join(diff_lines),
        }

    def apply_configure(self, dry_run: bool = False) -> tuple[bool, str]:
        """Apply PATH modifications and write eSim configuration file with diff recording."""
        preview = self.preview_configure()
        added_entries = preview["added_path_entries"]
        current_entries = preview["current_path_entries"]
        target_cfg_path = Path(preview["target_esim_cfg"])
        new_content = preview["new_cfg_content"]
        old_content = preview["old_cfg_content"]

        if dry_run:
            msg = (
                f"[DRY RUN] Would append {len(added_entries)} entries to user PATH and "
                f"update eSim configuration file at {target_cfg_path}."
            )
            log_action("configure", action="dry_run", result="SUCCESS", details=msg)
            return True, msg

        # Save record before applying changes
        record_data = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_user_path": current_entries,
            "added_path_entries": added_entries,
            "esim_config_path": str(target_cfg_path),
            "previous_esim_config_content": old_content if old_content else None,
        }
        self.record_file.write_text(json.dumps(record_data, indent=2), encoding="utf-8")

        # Update user PATH in HKCU
        if added_entries:
            updated_entries = list(current_entries) + added_entries
            set_user_path(updated_entries)

        # Write eSim configuration file
        target_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        target_cfg_path.write_text(new_content, encoding="utf-8")

        details = f"Added {len(added_entries)} PATH entries; wrote {target_cfg_path}."
        log_action("configure", action="apply", result="SUCCESS", details=details)
        return True, f"Configuration successfully applied. {details}"

    def preview_revert(self) -> dict[str, Any]:
        """Preview the revert of all tool-managed configuration changes."""
        if not self.record_file.is_file():
            raise ConfigError(
                "No configuration change record found. Nothing to revert.",
                fix_suggestion="Run 'esim-tool-manager configure' before attempting to revert.",
            )

        try:
            record_data = json.loads(self.record_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ConfigError(f"Configuration change record corrupted: {exc}") from exc

        original_path = record_data.get("original_user_path", [])
        added_entries = record_data.get("added_path_entries", [])
        cfg_path_str = record_data.get("esim_config_path")
        prev_cfg_content = record_data.get("previous_esim_config_content")

        current_path = get_user_path()
        current_cfg_content = ""
        if cfg_path_str and Path(cfg_path_str).is_file():
            current_cfg_content = Path(cfg_path_str).read_text(encoding="utf-8")

        diff_lines = list(
            difflib.unified_diff(
                current_cfg_content.splitlines(keepends=True),
                (prev_cfg_content or "").splitlines(keepends=True),
                fromfile="esim_config.ini (current)",
                tofile="esim_config.ini (reverted)",
            )
        )

        return {
            "original_path": original_path,
            "added_entries_to_remove": added_entries,
            "current_path": current_path,
            "esim_config_path": cfg_path_str,
            "previous_cfg_content": prev_cfg_content,
            "cfg_diff": "".join(diff_lines),
        }

    def apply_revert(self, dry_run: bool = False) -> tuple[bool, str]:
        """Revert user PATH and eSim configuration to pre-configured state."""
        preview = self.preview_revert()

        if dry_run:
            msg = (
                f"[DRY RUN] Would remove {len(preview['added_entries_to_remove'])} entries from user PATH "
                f"and restore eSim config at {preview['esim_config_path']}."
            )
            log_action("configure", action="revert_dry_run", result="SUCCESS", details=msg)
            return True, msg

        # Revert user PATH
        set_user_path(preview["original_path"])

        # Revert eSim config file
        cfg_path = Path(preview["esim_config_path"]) if preview["esim_config_path"] else None
        if cfg_path:
            if preview["previous_cfg_content"] is not None:
                cfg_path.write_text(preview["previous_cfg_content"], encoding="utf-8")
            elif cfg_path.is_file():
                try:
                    cfg_path.unlink()
                except OSError:
                    pass

        # Remove the change record file
        self.record_file.unlink(missing_ok=True)

        msg = "Configuration successfully reverted to original state."
        log_action("configure", action="revert", result="SUCCESS", details=msg)
        return True, msg
