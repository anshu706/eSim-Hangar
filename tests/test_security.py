r"""Comprehensive Security Abuse-Case Tests for eSim Automated Tool Manager.

Tests the security controls specified in Section 8 (Secure Vibe Coding):
1. Malformed tools.yaml
2. Shell injection attempt (e.g. "ngspice & del *")
3. Insecure non-HTTPS URL (e.g. "http://...")
4. Cryptographic checksum mismatch
5. Path-traversal attempt (e.g. "..\..\Windows")
6. Missing winget binary on system
7. Corrupted config.json file
8. Network failure mid-download
9. Disallowed URL domain
10. Authorization / Scope boundary enforcement
11. Secret redaction in action logs
"""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import yaml

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.downloader import Downloader
from esim_tool_manager.errors import (
    ConfigError,
    DownloadError,
    PlatformError,
    RegistryError,
    ValidationError,
)
from esim_tool_manager.logger import log_action, read_logs, setup_logger
from esim_tool_manager.platform_win import check_winget_installed
from esim_tool_manager.registry import ToolRegistry
from esim_tool_manager.validators import (
    validate_download_url,
    validate_safe_path,
    validate_tool_name,
)


# Test 1: Malformed tools.yaml
def test_abuse_case_1_malformed_tools_yaml(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "tools.yaml"
    bad_yaml.write_text("tools: [invalid mapping: {}}", encoding="utf-8")
    with pytest.raises(RegistryError, match="syntax"):
        ToolRegistry(yaml_path=bad_yaml)


# Test 2: Shell injection in tool name or command
def test_abuse_case_2_shell_injection(tmp_path: Path) -> None:
    malicious_names = [
        "ngspice & del *",
        "kicad; calc.exe",
        "python && rm -rf /",
        "tool | dir",
        "`whoami`",
        "$(whoami)",
    ]
    for bad_name in malicious_names:
        with pytest.raises(ValidationError, match="Invalid tool name"):
            validate_tool_name(bad_name)

    # In tools.yaml
    bad_data = {
        "version": "1.0",
        "tools": {
            "ngspice & del *": {
                "name": "ngspice & del *",
                "binary": "ngspice.exe",
                "minimum_version": "1.0",
                "pinned_version": "1.0",
                "install": {"method": "winget", "package_id": "test"},
            }
        },
    }
    yaml_file = tmp_path / "injection.yaml"
    yaml_file.write_text(yaml.dump(bad_data), encoding="utf-8")
    with pytest.raises(ValidationError, match="Invalid tool name"):
        ToolRegistry(yaml_path=yaml_file)


# Test 3: Insecure non-HTTPS URL
def test_abuse_case_3_non_https_url() -> None:
    insecure_urls = [
        "http://downloads.sourceforge.net/project/ngspice/tool.zip",
        "ftp://downloads.sourceforge.net/project/ngspice/tool.zip",
        "file:///C:/Windows/System32/cmd.exe",
    ]
    for url in insecure_urls:
        with pytest.raises(ValidationError, match="Insecure URL scheme"):
            validate_download_url(url)


# Test 4: Checksum mismatch (corrupted download deleted immediately)
def test_abuse_case_4_checksum_mismatch(tmp_path: Path) -> None:
    downloader = Downloader(cache_dir=tmp_path)
    content = b"Tampered binary contents"
    wrong_hash = "0" * 64

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": str(len(content))}
    mock_resp.iter_content = MagicMock(return_value=[content])
    mock_resp.__enter__.return_value = mock_resp

    with (
        patch("requests.get", return_value=mock_resp),
        pytest.raises(DownloadError, match="checksum mismatch"),
    ):
        downloader.download(
            url="https://downloads.sourceforge.net/project/ngspice/ngspice.zip",
            expected_sha256=wrong_hash,
            filename="ngspice.zip",
            show_progress=False,
        )

    # Corrupt files must be deleted with no leftovers
    assert not (tmp_path / "ngspice.zip").exists()
    assert not (tmp_path / "ngspice.zip.part").exists()


# Test 5: Path-traversal attempt
def test_abuse_case_5_path_traversal() -> None:
    traversal_attempts = [
        r"..\..\Windows\System32",
        r"C:\FOSSEE\..\..\Windows",
        r"foo/../../bar",
        r"tools/../../../Users",
    ]
    for path_str in traversal_attempts:
        with pytest.raises(ValidationError, match="Path traversal detected"):
            validate_safe_path(path_str)


# Test 6: Missing winget binary on system
def test_abuse_case_6_missing_winget() -> None:
    with patch("shutil.which", return_value=None):
        with pytest.raises(PlatformError) as exc_info:
            check_winget_installed()
        assert "not installed" in exc_info.value.message
        assert "Microsoft Store" in (exc_info.value.fix_suggestion or "")


# Test 7: Corrupted user configuration file
def test_abuse_case_7_corrupted_config(tmp_path: Path) -> None:
    mgr = ConfigManager(config_dir=tmp_path)
    mgr.initialize_directories()
    mgr.config_path.write_text("{ unclosed json: [1, 2, ", encoding="utf-8")

    with pytest.raises(ConfigError, match="corrupted"):
        mgr.load_config()


# Test 8: Network failure mid-download with retries
def test_abuse_case_8_network_failure_mid_download(tmp_path: Path) -> None:
    downloader = Downloader(cache_dir=tmp_path, max_retries=2, backoff_factor=0.01)
    expected_hash = hashlib.sha256(b"dummy").hexdigest()

    with (
        patch("requests.get", side_effect=requests.ConnectionError("Connection dropped")),
        pytest.raises(DownloadError, match="Failed to download"),
    ):
        downloader.download(
            url="https://downloads.sourceforge.net/project/ngspice/ngspice.zip",
            expected_sha256=expected_hash,
            filename="ngspice.zip",
            show_progress=False,
        )

    # Partial file should not remain as completed installer
    assert not (tmp_path / "ngspice.zip").exists()


# Test 9: Disallowed URL domain
def test_abuse_case_9_disallowed_domain() -> None:
    disallowed_urls = [
        "https://evil-hacker-site.org/malware.exe",
        "https://sourceforge.net.evil.com/fake.zip",
        "https://pastebin.com/raw/exploit",
    ]
    for url in disallowed_urls:
        with pytest.raises(ValidationError, match="not in the allowed download domains"):
            validate_download_url(url)


# Test 10: Scope and authorization guard
def test_abuse_case_10_authorization_scope(tmp_path: Path) -> None:
    allowed_parent = tmp_path / "allowed_scope"
    allowed_parent.mkdir()
    restricted_dir = tmp_path / "system_dir"
    restricted_dir.mkdir()

    # Accessing outside allowed parent raises ValidationError
    with pytest.raises(ValidationError, match="outside allowed directories"):
        validate_safe_path(restricted_dir / "target.txt", allowed_parents=[allowed_parent])


# Test 11: Secrets redaction in action logs
def test_abuse_case_11_secrets_redaction(tmp_path: Path) -> None:
    setup_logger(log_dir=tmp_path, debug_mode=True)
    sensitive_info = "Using API token: ghp_SECRET1234567890 and password: MySecretPassword"
    log_action(
        "test_cmd",
        tool="git",
        action="test",
        result="SUCCESS",
        details=sensitive_info,
        log_dir=tmp_path,
    )

    entries = read_logs(tail=5, log_dir=tmp_path)
    assert len(entries) >= 1
    logged_details = entries[-1].get("details", "")
    assert "ghp_SECRET" not in logged_details
    assert "MySecretPassword" not in logged_details
    assert "[REDACTED]" in logged_details
