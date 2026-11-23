"""Custom exceptions for eSim Automated Tool Manager."""

from typing import Optional


class EsimToolManagerError(Exception):
    """Base exception for all esim-tool-manager errors."""

    def __init__(self, message: str, fix_suggestion: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.fix_suggestion = fix_suggestion

    def __str__(self) -> str:
        if self.fix_suggestion:
            return f"{self.message}\nSuggested fix: {self.fix_suggestion}"
        return self.message


class ValidationError(EsimToolManagerError):
    """Raised when an input or parameter fails security or format validation."""


class ConfigError(EsimToolManagerError):
    """Raised when loading, parsing, or saving configuration fails."""


class RegistryError(EsimToolManagerError):
    """Raised when tools.yaml cannot be found, parsed, or validated."""


class ToolNotFoundError(EsimToolManagerError):
    """Raised when a tool is not installed or its binary is missing."""


class IncompatibleVersionError(EsimToolManagerError):
    """Raised when an installed tool does not meet minimum version requirements."""


class DependencyError(EsimToolManagerError):
    """Raised when a declared prerequisite dependency is missing or incompatible."""


class PlatformError(EsimToolManagerError):
    """Raised when a platform-specific command or operation (e.g. winget, registry) fails."""


class DownloadError(EsimToolManagerError):
    """Raised when a download, verification, or extraction fails."""


class RollbackError(EsimToolManagerError):
    """Raised when rolling back a tool installation fails."""
