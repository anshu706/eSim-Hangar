"""Input validation and security controls for eSim Tool Manager."""

import re
from pathlib import Path
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

from esim_tool_manager.errors import ValidationError

TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
VERSION_PATTERN = re.compile(r"^[0-9]+(\.[0-9]+)*([a-zA-Z0-9.+_-]*)$")
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")

ALLOWED_URL_DOMAINS = {
    "sourceforge.net",
    "downloads.sourceforge.net",
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "kicad.org",
    "www.kicad.org",
    "python.org",
    "www.python.org",
}


def validate_tool_name(name: str) -> str:
    """Validate that a tool name contains only lowercase alphanumeric characters and hyphens."""
    if not isinstance(name, str) or not TOOL_NAME_PATTERN.match(name):
        raise ValidationError(
            f"Invalid tool name '{name}'. Tool names must match ^[a-z0-9-]+$",
            fix_suggestion="Use only lowercase letters, digits, and hyphens (e.g., 'ngspice', 'kicad').",
        )
    return name


def validate_version_string(version_str: str) -> str:
    """Validate that a version string is safe, well-formed, and parses with packaging.version."""
    if not isinstance(version_str, str) or not version_str.strip():
        raise ValidationError("Version string cannot be empty.")

    clean_version = version_str.strip()
    if not VERSION_PATTERN.match(clean_version):
        raise ValidationError(
            f"Invalid version format '{version_str}'. Must follow standard semantic versioning.",
            fix_suggestion="Provide a valid version format like '43.0' or '3.11.9'.",
        )
    try:
        Version(clean_version)
    except InvalidVersion as exc:
        raise ValidationError(
            f"Version string '{version_str}' is not a valid packaging version: {exc}",
            fix_suggestion="Use standard version numbers (e.g. 1.2.3).",
        ) from exc
    return clean_version


def validate_download_url(url: str) -> str:
    """Validate that a download URL uses HTTPS and belongs to the domain allowlist."""
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("Download URL cannot be empty.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https":
        raise ValidationError(
            f"Insecure URL scheme '{parsed.scheme}'. Only HTTPS is permitted.",
            fix_suggestion="Update URL to start with 'https://'.",
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValidationError(f"URL '{url}' does not contain a valid hostname.")

    # Match exact domain or allowed subdomains
    domain_allowed = any(
        hostname == domain or hostname.endswith("." + domain) for domain in ALLOWED_URL_DOMAINS
    )
    if not domain_allowed:
        raise ValidationError(
            f"Host '{hostname}' is not in the allowed download domains: {sorted(ALLOWED_URL_DOMAINS)}",
            fix_suggestion="Ensure the download URL points to an official sourceforge, github, kicad, or python host.",
        )

    return url.strip()


def validate_sha256(checksum: str) -> str:
    """Validate that a SHA256 string is 64 hex characters."""
    if not isinstance(checksum, str) or not SHA256_PATTERN.match(checksum.strip()):
        raise ValidationError(
            f"Invalid SHA256 checksum '{checksum}'. Expected 64 hexadecimal characters.",
            fix_suggestion="Verify and supply a 64-character SHA256 hash.",
        )
    return checksum.strip().lower()


def validate_safe_path(path: str | Path, allowed_parents: list[Path] | None = None) -> Path:
    """Ensure path has no traversal ('..') and resolves inside allowed boundaries if specified."""
    str_path = str(path)
    # Explicitly reject any relative traversal components
    path_parts = str_path.replace("\\", "/").split("/")
    if ".." in path_parts:
        raise ValidationError(
            f"Path traversal detected in path '{str_path}'. Paths containing '..' are strictly prohibited.",
            fix_suggestion="Use an absolute path or a safe relative path without '..'.",
        )

    resolved = Path(str_path).resolve()

    if allowed_parents:
        is_safe = False
        for parent in allowed_parents:
            try:
                resolved_parent = parent.resolve()
                if resolved == resolved_parent or resolved.is_relative_to(resolved_parent):
                    is_safe = True
                    break
            except (ValueError, RuntimeError):
                continue
        if not is_safe:
            raise ValidationError(
                f"Path '{resolved}' is outside allowed directories: {[str(p) for p in allowed_parents]}",
                fix_suggestion="Specify a path inside the user profile or eSim tool directory.",
            )

    return resolved
