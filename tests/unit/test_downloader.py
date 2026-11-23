"""Unit tests for resilient downloader."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from esim_tool_manager.downloader import (
    Downloader,
    compute_sha256,
    verify_sha256,
)
from esim_tool_manager.errors import DownloadError


def test_compute_and_verify_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "sample.bin"
    test_file.write_bytes(b"eSim EDA Simulation Test Content")

    expected_hash = hashlib.sha256(b"eSim EDA Simulation Test Content").hexdigest().lower()
    assert compute_sha256(test_file) == expected_hash
    assert verify_sha256(test_file, expected_hash) is True
    assert verify_sha256(test_file, "0" * 64) is False


def test_downloader_cache_hit(tmp_path: Path) -> None:
    downloader = Downloader(cache_dir=tmp_path)
    content = b"Cached installer content"
    expected_hash = hashlib.sha256(content).hexdigest().lower()

    cached_file = tmp_path / "tool.zip"
    cached_file.write_bytes(content)

    with patch("requests.get") as mock_get:
        result = downloader.download(
            url="https://downloads.sourceforge.net/project/ngspice/tool.zip",
            expected_sha256=expected_hash,
            filename="tool.zip",
        )
        assert result == cached_file
        # Cache hit must NOT invoke network requests!
        mock_get.assert_not_called()


def test_downloader_successful_download(tmp_path: Path) -> None:
    downloader = Downloader(cache_dir=tmp_path)
    content = b"Freshly downloaded package"
    expected_hash = hashlib.sha256(content).hexdigest().lower()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": str(len(content))}
    mock_resp.iter_content = MagicMock(return_value=[content])
    mock_resp.__enter__.return_value = mock_resp

    with patch("requests.get", return_value=mock_resp):
        result = downloader.download(
            url="https://downloads.sourceforge.net/project/ngspice/tool.zip",
            expected_sha256=expected_hash,
            filename="fresh_tool.zip",
            show_progress=False,
        )
        assert result.is_file()
        assert result.read_bytes() == content


def test_downloader_checksum_mismatch_deletes_file(tmp_path: Path) -> None:
    downloader = Downloader(cache_dir=tmp_path)
    content = b"Corrupted content"
    wrong_hash = "f" * 64

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": str(len(content))}
    mock_resp.iter_content = MagicMock(return_value=[content])
    mock_resp.__enter__.return_value = mock_resp

    with (
        patch("requests.get", return_value=mock_resp),
        pytest.raises(DownloadError, match="SHA-256 checksum mismatch"),
    ):
        downloader.download(
            url="https://downloads.sourceforge.net/project/ngspice/bad.zip",
            expected_sha256=wrong_hash,
            filename="bad.zip",
            show_progress=False,
        )

    # File and .part file must be removed for safety
    assert not (tmp_path / "bad.zip").exists()
    assert not (tmp_path / "bad.zip.part").exists()


def test_downloader_cache_list_and_clear(tmp_path: Path) -> None:
    downloader = Downloader(cache_dir=tmp_path)
    (tmp_path / "file1.zip").write_bytes(b"data1")
    (tmp_path / "file2.7z").write_bytes(b"data2")
    (tmp_path / "file3.part").write_bytes(b"partial")

    items = downloader.list_cached_files()
    assert len(items) == 2
    filenames = [i["filename"] for i in items]
    assert "file1.zip" in filenames
    assert "file2.7z" in filenames
    assert "file3.part" not in filenames

    deleted_count = downloader.clear_cache()
    assert deleted_count == 3
    assert len(downloader.list_cached_files()) == 0
