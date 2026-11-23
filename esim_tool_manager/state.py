"""Installation state tracking and history for rollbacks."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.errors import EsimToolManagerError
from esim_tool_manager.validators import validate_tool_name


@dataclass
class InstallRecord:
    """Metadata recorded for an installed tool."""

    tool_name: str
    version: str
    install_method: str  # "winget" or "direct_download"
    install_path: str | None
    installed_at: str
    previous_version: str | None = None
    previous_path: str | None = None
    previous_method: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstallRecord":
        """Instantiate record from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            version=data["version"],
            install_method=data.get("install_method", "unknown"),
            install_path=data.get("install_path"),
            installed_at=data.get("installed_at", datetime.now(timezone.utc).isoformat()),
            previous_version=data.get("previous_version"),
            previous_path=data.get("previous_path"),
            previous_method=data.get("previous_method"),
        )


class StateManager:
    """Manages reading and writing install records in %LOCALAPPDATA%\\esim-tool-manager\\state."""

    def __init__(self, state_dir: Path | None = None, config_mgr: ConfigManager | None = None):
        if state_dir:
            self.state_dir = state_dir
        else:
            cfg = config_mgr or ConfigManager()
            self.state_dir = cfg.state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_tool_file(self, tool_name: str) -> Path:
        validate_tool_name(tool_name)
        return self.state_dir / f"{tool_name}.json"

    def get_record(self, tool_name: str) -> InstallRecord | None:
        """Retrieve current install record for a tool."""
        record_file = self._get_tool_file(tool_name)
        if not record_file.is_file():
            return None
        try:
            with open(record_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return InstallRecord.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def save_record(
        self,
        tool_name: str,
        version: str,
        install_method: str,
        install_path: str | None,
    ) -> InstallRecord:
        """Create and persist a new install record, archiving previous record if present."""
        validate_tool_name(tool_name)
        existing = self.get_record(tool_name)

        prev_version = existing.version if existing else None
        prev_path = existing.install_path if existing else None
        prev_method = existing.install_method if existing else None

        record = InstallRecord(
            tool_name=tool_name,
            version=version,
            install_method=install_method,
            install_path=install_path,
            installed_at=datetime.now(timezone.utc).isoformat(),
            previous_version=prev_version,
            previous_path=prev_path,
            previous_method=prev_method,
        )

        record_file = self._get_tool_file(tool_name)
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=str(self.state_dir), delete=False, encoding="utf-8"
            ) as tf:
                temp_file = tf.name
                json.dump(record.to_dict(), tf, indent=2)
            os.replace(temp_file, str(record_file))
        except OSError as exc:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            raise EsimToolManagerError(
                f"Failed to save state record for '{tool_name}': {exc}",
                fix_suggestion="Check filesystem permissions in state directory.",
            ) from exc

        return record

    def delete_record(self, tool_name: str) -> bool:
        """Delete install record file."""
        record_file = self._get_tool_file(tool_name)
        if record_file.is_file():
            try:
                record_file.unlink()
                return True
            except OSError:
                return False
        return False

    def get_all_records(self) -> dict[str, InstallRecord]:
        """Load all saved install records."""
        records: dict[str, InstallRecord] = {}
        for p in self.state_dir.glob("*.json"):
            tool_name = p.stem
            rec = self.get_record(tool_name)
            if rec:
                records[tool_name] = rec
        return records
