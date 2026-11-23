"""Unit tests for security validators."""

from pathlib import Path

import pytest

from esim_tool_manager.errors import ValidationError
from esim_tool_manager.validators import (
    validate_download_url,
    validate_safe_path,
    validate_sha256,
    validate_tool_name,
    validate_version_string,
)


def test_validate_tool_name_valid() -> None:
    assert validate_tool_name("ngspice") == "ngspice"
    assert validate_tool_name("kicad-cli") == "kicad-cli"
    assert validate_tool_name("python3") == "python3"


def test_validate_tool_name_invalid() -> None:
    with pytest.raises(ValidationError):
        validate_tool_name("ngspice & del *")
    with pytest.raises(ValidationError):
        validate_tool_name("Tool_Name")
    with pytest.raises(ValidationError):
        validate_tool_name("../../etc/passwd")
    with pytest.raises(ValidationError):
        validate_tool_name("")


def test_validate_version_string_valid() -> None:
    assert validate_version_string("3.11.9") == "3.11.9"
    assert validate_version_string("43.0") == "43.0"
    assert validate_version_string("8.0.1") == "8.0.1"


def test_validate_version_string_invalid() -> None:
    with pytest.raises(ValidationError):
        validate_version_string("")
    with pytest.raises(ValidationError):
        validate_version_string("version-1.0; rm -rf")
    with pytest.raises(ValidationError):
        validate_version_string("not_a_version")


def test_validate_download_url_valid() -> None:
    valid_url = "https://downloads.sourceforge.net/project/ngspice/ngspice-43_64.7z"
    assert validate_download_url(valid_url) == valid_url
    github_url = "https://github.com/microsoft/winget-cli/releases"
    assert validate_download_url(github_url) == github_url


def test_validate_download_url_insecure() -> None:
    with pytest.raises(ValidationError, match="Insecure URL scheme"):
        validate_download_url("http://downloads.sourceforge.net/project/ngspice/test.zip")


def test_validate_download_url_unauthorized_domain() -> None:
    with pytest.raises(ValidationError, match="not in the allowed download domains"):
        validate_download_url("https://malicious-site.com/installer.exe")


def test_validate_sha256_valid() -> None:
    h = "fc3d4d418499c9b807f0f3032c55537d628d03d86c3f2a742735487497ecb5c0"
    assert validate_sha256(h) == h
    assert validate_sha256(h.upper()) == h


def test_validate_sha256_invalid() -> None:
    with pytest.raises(ValidationError):
        validate_sha256("short_hash")
    with pytest.raises(ValidationError):
        validate_sha256("zzzz4d418499c9b807f0f3032c55537d628d03d86c3f2a742735487497ecb5c0")


def test_validate_safe_path_rejects_traversal() -> None:
    with pytest.raises(ValidationError, match="Path traversal detected"):
        validate_safe_path(r"..\..\Windows\System32")
    with pytest.raises(ValidationError, match="Path traversal detected"):
        validate_safe_path("foo/../bar")


def test_validate_safe_path_allowed_parents(tmp_path: Path) -> None:
    safe_child = tmp_path / "subdir" / "file.txt"
    safe_child.parent.mkdir(parents=True)
    safe_child.touch()
    assert validate_safe_path(safe_child, allowed_parents=[tmp_path]) == safe_child.resolve()

    outside_path = Path("C:/Windows/System32")
    with pytest.raises(ValidationError, match="outside allowed directories"):
        validate_safe_path(outside_path, allowed_parents=[tmp_path])
