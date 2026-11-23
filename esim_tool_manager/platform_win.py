"""Windows-specific platform abstractions for eSim Tool Manager."""

import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Optional
import winreg

from esim_tool_manager.errors import PlatformError


def is_windows() -> bool:
    """Return True if running on Windows."""
    return sys.platform.startswith("win")


def is_admin() -> bool:
    """Check if the current process has administrative privileges."""
    if not is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False


def get_winget_path() -> Optional[str]:
    """Find the path to the winget executable."""
    return shutil.which("winget.exe") or shutil.which("winget")


def check_winget_installed() -> str:
    """Verify winget is available, returning its version string or raising PlatformError."""
    winget = get_winget_path()
    if not winget:
        raise PlatformError(
            "Windows Package Manager (winget) is not installed or not in PATH.",
            fix_suggestion=(
                "Install or update 'App Installer' from the Microsoft Store, or download "
                "winget directly from: https://github.com/microsoft/winget-cli/releases"
            ),
        )
    try:
        proc = subprocess.run(
            [winget, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            raise PlatformError(
                f"winget execution failed with code {proc.returncode}: {proc.stderr.strip()}",
                fix_suggestion="Ensure winget is properly installed and functioning.",
            )
        return proc.stdout.strip()
    except subprocess.SubprocessError as exc:
        raise PlatformError(
            f"Failed to execute winget: {exc}",
            fix_suggestion="Check winget installation or run in an updated Windows Terminal.",
        ) from exc


def check_git_installed() -> str:
    """Verify Git is available, returning its version string or raising PlatformError."""
    git_bin = shutil.which("git.exe") or shutil.which("git")
    if not git_bin:
        raise PlatformError(
            "Git is not found on PATH.",
            fix_suggestion="Install Git via 'esim-tool-manager install git' or download from https://git-scm.com.",
        )
    try:
        proc = subprocess.run(
            [git_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.stdout.strip()
    except subprocess.SubprocessError as exc:
        raise PlatformError(f"Failed to execute git: {exc}") from exc


def get_user_path() -> list[str]:
    """Read the current user PATH from HKCU\\Environment."""
    if not is_windows():
        return os.environ.get("PATH", "").split(os.pathsep)

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            try:
                val, reg_type = winreg.QueryValueEx(key, "Path")
                return [p.strip() for p in val.split(";") if p.strip()]
            except FileNotFoundError:
                return []
    except OSError as exc:
        raise PlatformError(
            f"Failed to read user PATH from registry: {exc}",
            fix_suggestion="Check HKCU\\Environment registry permissions.",
        ) from exc


def set_user_path(paths: list[str]) -> None:
    """Write the updated user PATH to HKCU\\Environment and broadcast settings change."""
    if not is_windows():
        return

    # Deduplicate while preserving order
    deduped: list[str] = []
    for p in paths:
        norm = str(Path(p))
        if norm not in deduped and p.strip():
            deduped.append(norm)

    new_path_str = ";".join(deduped)

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE | winreg.KEY_READ
        ) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path_str)
    except OSError as exc:
        raise PlatformError(
            f"Failed to write user PATH to registry: {exc}",
            fix_suggestion="Ensure current user has write access to HKCU\\Environment.",
        ) from exc

    broadcast_environment_change()


def broadcast_environment_change() -> None:
    """Notify open Windows processes that environment variables have changed."""
    if not is_windows():
        return
    try:
        hwnd_broadcast = 0xFFFF
        wm_settingchange = 0x001A
        smto_abortifhung = 0x0002
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            hwnd_broadcast,
            wm_settingchange,
            0,
            "Environment",
            smto_abortifhung,
            5000,
            ctypes.byref(result),
        )
    except (AttributeError, OSError):
        pass


def run_command_safe(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Execute a command without shell=True, returning CompletedProcess."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PlatformError(
            f"Command '{' '.join(cmd)}' timed out after {timeout} seconds.",
            fix_suggestion="Check network or system responsiveness.",
        ) from exc
    except OSError as exc:
        raise PlatformError(
            f"Failed to run command '{cmd[0]}': {exc}",
            fix_suggestion=f"Verify that '{cmd[0]}' is installed and accessible.",
        ) from exc
