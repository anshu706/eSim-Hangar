"""Rotating action log implementation for eSim Tool Manager."""

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from typing import Any, Optional

MAX_LOG_BYTES = 1024 * 1024  # 1 MB
BACKUP_COUNT = 5

_LOGGER: Optional[logging.Logger] = None


def get_default_log_dir() -> Path:
    """Return the default log directory inside %LOCALAPPDATA%."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    log_dir = base / "esim-tool-manager" / "logs"
    return log_dir


def setup_logger(log_dir: Optional[Path] = None, debug_mode: bool = False) -> logging.Logger:
    """Configure and return the rotating action logger."""
    global _LOGGER
    target_dir = log_dir or get_default_log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "actions.log"

    logger = logging.getLogger("esim_tool_manager")
    logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    # Avoid duplicate handlers if setup is called multiple times
    if not logger.handlers:
        handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _LOGGER = logger
    return logger


def log_action(
    command: str,
    tool: Optional[str] = None,
    action: str = "",
    result: str = "SUCCESS",
    details: Optional[str] = None,
    log_dir: Optional[Path] = None,
) -> None:
    """Record a structured action entry in the rotating log file."""
    logger = _LOGGER or setup_logger(log_dir=log_dir)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Strip potential sensitive patterns if any
    safe_details = details or ""
    for secret_key in ["token", "password", "apikey", "secret"]:
        if secret_key in safe_details.lower():
            safe_details = "[REDACTED]"

    entry = {
        "timestamp": timestamp,
        "command": command,
        "tool": tool or "all",
        "action": action,
        "result": result,
        "details": safe_details,
    }
    log_msg = json.dumps(entry, ensure_ascii=False)
    if result.upper() == "SUCCESS":
        logger.info(log_msg)
    else:
        logger.error(log_msg)


def read_logs(tail: int = 50, log_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """Read and parse the most recent log entries."""
    target_dir = log_dir or get_default_log_dir()
    log_file = target_dir / "actions.log"
    if not log_file.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []

    for line in lines[-tail:]:
        line_str = line.strip()
        if not line_str:
            continue
        # Format is "<asctime> [<level>] <json_content>"
        try:
            bracket_idx = line_str.find("] ")
            if bracket_idx != -1:
                json_part = line_str[bracket_idx + 2 :]
                entry = json.loads(json_part)
                entries.append(entry)
            else:
                entries.append({"raw": line_str})
        except json.JSONDecodeError:
            entries.append({"raw": line_str})

    return entries
