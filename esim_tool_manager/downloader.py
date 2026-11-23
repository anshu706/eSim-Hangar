"""Resilient downloader with exponential backoff, HTTP Range resume, and SHA256 integrity."""

import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

from esim_tool_manager.config import ConfigManager
from esim_tool_manager.errors import DownloadError
from esim_tool_manager.validators import validate_download_url, validate_sha256

CHUNK_SIZE = 64 * 1024  # 64 KB chunks
DEFAULT_MAX_RETRIES = 4
DEFAULT_BACKOFF = 1.5


def compute_sha256(file_path: Path) -> str:
    """Compute and return lowercase hex SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def verify_sha256(file_path: Path, expected_sha256: str) -> bool:
    """Check whether a file matches the expected SHA-256 checksum."""
    if not file_path.is_file():
        return False
    computed = compute_sha256(file_path)
    return computed == expected_sha256.strip().lower()


class Downloader:
    """Handles reliable file downloads with resuming, caching, and integrity verification."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF,
        config_mgr: ConfigManager | None = None,
    ):
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            cfg = config_mgr or ConfigManager()
            self.cache_dir = cfg.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _get_filename_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        name = os.path.basename(parsed.path)
        if not name or "." not in name:
            name = "downloaded_installer.bin"
        return name

    def download(
        self,
        url: str,
        expected_sha256: str,
        filename: str | None = None,
        show_progress: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Download file with resume support, retry logic, and SHA-256 validation."""
        valid_url = validate_download_url(url)
        clean_sha256 = validate_sha256(expected_sha256)

        target_name = filename or self._get_filename_from_url(valid_url)
        target_path = self.cache_dir / target_name
        part_path = self.cache_dir / f"{target_name}.part"

        # 1. Offline Cache Check
        if target_path.is_file():
            if verify_sha256(target_path, clean_sha256):
                return target_path
            # Corrupted cache entry; remove and re-download
            try:
                target_path.unlink()
            except OSError:
                pass

        # 2. Resumable Download Loop with Retries
        attempts = 0
        last_error: Exception | None = None

        while attempts < self.max_retries:
            attempts += 1
            existing_bytes = part_path.stat().st_size if part_path.is_file() else 0
            headers: dict[str, str] = {}
            mode = "ab"

            if existing_bytes > 0:
                headers["Range"] = f"bytes={existing_bytes}-"

            try:
                with requests.get(
                    valid_url,
                    headers=headers,
                    stream=True,
                    timeout=30,
                    allow_redirects=True,
                ) as resp:
                    # Handle range response
                    if resp.status_code == 416:  # Range Not Satisfiable (corrupt or completed)
                        part_path.unlink(missing_ok=True)
                        existing_bytes = 0
                        mode = "wb"
                        resp = requests.get(
                            valid_url, stream=True, timeout=30, allow_redirects=True
                        )

                    if resp.status_code not in (200, 206):
                        raise DownloadError(
                            f"HTTP download request failed with status code {resp.status_code}",
                            fix_suggestion="Check server availability or network connection.",
                        )

                    # If server ignores Range header and returns 200, restart from byte 0
                    if resp.status_code == 200 and existing_bytes > 0:
                        existing_bytes = 0
                        mode = "wb"

                    total_size = int(resp.headers.get("content-length", 0)) + existing_bytes

                    if HAVE_RICH and show_progress and not progress_callback:
                        self._stream_with_rich_progress(
                            resp, part_path, mode, existing_bytes, total_size, target_name
                        )
                    else:
                        self._stream_to_file(
                            resp, part_path, mode, existing_bytes, total_size, progress_callback
                        )

                # Successful download stream completed
                break

            except (requests.RequestException, DownloadError, OSError) as exc:
                last_error = exc
                if attempts >= self.max_retries:
                    break
                sleep_sec = self.backoff_factor**attempts
                time.sleep(sleep_sec)

        if not part_path.is_file():
            raise DownloadError(
                f"Failed to download '{target_name}' after {self.max_retries} attempts: {last_error}",
                fix_suggestion="Check internet connection and retry, or place pre-downloaded installer in cache.",
            )

        # 3. Cryptographic Verification
        if not verify_sha256(part_path, clean_sha256):
            part_path.unlink(missing_ok=True)
            raise DownloadError(
                f"SHA-256 checksum mismatch for downloaded file '{target_name}'. File was deleted for safety.",
                fix_suggestion="Verify the expected hash in tools.yaml or re-download.",
            )

        # Atomically move verified file into place
        if target_path.exists():
            target_path.unlink()
        part_path.rename(target_path)
        return target_path

    def _stream_to_file(
        self,
        resp: requests.Response,
        part_path: Path,
        mode: str,
        initial_bytes: int,
        total_size: int,
        callback: Callable[[int, int], None] | None,
    ) -> None:
        downloaded = initial_bytes
        with open(part_path, mode) as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if callback:
                        callback(downloaded, total_size)

    def _stream_with_rich_progress(
        self,
        resp: requests.Response,
        part_path: Path,
        mode: str,
        initial_bytes: int,
        total_size: int,
        filename: str,
    ) -> None:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(
                f"Downloading {filename}", total=total_size or None, completed=initial_bytes
            )
            with open(part_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

    def list_cached_files(self) -> list[dict[str, Any]]:
        """List all files present in the local cache."""
        items: list[dict[str, Any]] = []
        for p in self.cache_dir.iterdir():
            if p.is_file() and not p.name.endswith(".part"):
                items.append(
                    {
                        "filename": p.name,
                        "size_bytes": p.stat().st_size,
                        "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                        "path": str(p.resolve()),
                    }
                )
        return items

    def clear_cache(self) -> int:
        """Delete all cached files and return count of deleted files."""
        count = 0
        for p in self.cache_dir.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                    count += 1
                except OSError:
                    pass
        return count
