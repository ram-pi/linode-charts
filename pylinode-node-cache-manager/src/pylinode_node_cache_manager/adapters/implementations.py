"""
Placeholder adapter implementations.
Full implementations will be added in subsequent steps.
"""

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from ..models import CacheEntry
from .base import DownloadAdapter


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class HuggingFaceAdapter(DownloadAdapter):
    """Download adapter for Hugging Face models."""

    def __init__(self, token: Optional[str] = None):
        self.token = token

    async def download(
        self,
        entry: CacheEntry,
        destination: Path,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Download a Hugging Face repo snapshot into destination directory."""
        try:
            from huggingface_hub import snapshot_download
        except Exception:
            return False, "huggingface_hub not installed; add dependency to enable HF downloads"

        destination.mkdir(parents=True, exist_ok=True)

        def _run_snapshot_download() -> None:
            token = os.getenv("HF_TOKEN") or self.token
            snapshot_download(
                repo_id=entry.ref,
                local_dir=str(destination),
                token=token,
                local_dir_use_symlinks=False,
            )

        try:
            await asyncio.to_thread(_run_snapshot_download)
            return True, None
        except Exception as e:
            return False, f"Hugging Face download failed: {e}"

    async def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Verify SHA256 checksum for single-file downloads."""
        if not path.is_file():
            return False
        return _file_sha256(path) == expected_sha256.lower()


class S3Adapter(DownloadAdapter):
    """Download adapter for AWS S3."""

    def __init__(self, access_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.access_key = access_key
        self.secret_key = secret_key

    async def download(
        self,
        entry: CacheEntry,
        destination: Path,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Download a single S3 object to destination file."""
        try:
            import boto3
        except Exception:
            return False, "boto3 not installed; add dependency to enable S3 downloads"

        if not entry.ref.startswith("s3://"):
            return False, f"Invalid S3 ref: {entry.ref}"

        stripped = entry.ref[len("s3://") :]
        parts = stripped.split("/", 1)
        if len(parts) != 2:
            return False, f"Invalid S3 ref format, expected s3://bucket/key: {entry.ref}"
        bucket, key = parts

        destination.parent.mkdir(parents=True, exist_ok=True)

        access_key = os.getenv("AWS_ACCESS_KEY_ID") or self.access_key
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or self.secret_key
        session_token = os.getenv("AWS_SESSION_TOKEN")

        session_kwargs = {}
        if access_key and secret_key:
            session_kwargs["aws_access_key_id"] = access_key
            session_kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            session_kwargs["aws_session_token"] = session_token

        def _download() -> None:
            client = boto3.client("s3", **session_kwargs)
            client.download_file(bucket, key, str(destination))

        try:
            await asyncio.to_thread(_download)
            return True, None
        except Exception as e:
            return False, f"S3 download failed: {e}"

    async def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Verify SHA256 checksum for single-file downloads."""
        if not path.is_file():
            return False
        return _file_sha256(path) == expected_sha256.lower()


class HTTPSAdapter(DownloadAdapter):
    """Download adapter for HTTPS URLs."""

    def __init__(self, timeout: int = 3600):
        self.timeout = timeout

    async def download(
        self,
        entry: CacheEntry,
        destination: Path,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Download a file from HTTPS URL to destination file."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_suffix(destination.suffix + ".partial")

        headers = {}
        bearer = os.getenv("HTTPS_BEARER_TOKEN")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        try:
            timeout = httpx.Timeout(self.timeout)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with client.stream("GET", entry.ref, headers=headers) as response:
                    response.raise_for_status()
                    with temp_path.open("wb") as f:
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                f.write(chunk)

            temp_path.replace(destination)
            return True, None
        except Exception as e:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            return False, f"HTTPS download failed: {e}"

    async def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Verify SHA256 checksum for downloaded file."""
        if not path.is_file():
            return False
        return _file_sha256(path) == expected_sha256.lower()


class OCIAdapter(DownloadAdapter):
    """Download adapter for OCI artifacts using ORAS."""

    def __init__(self):
        self.oras_binary = shutil.which("oras")

    async def download(
        self,
        entry: CacheEntry,
        destination: Path,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Download OCI artifact using ORAS if available."""
        if not self.oras_binary:
            return False, "OCI download requires 'oras' binary in PATH"

        destination.mkdir(parents=True, exist_ok=True)

        try:
            proc = await asyncio.create_subprocess_exec(
                self.oras_binary,
                "pull",
                entry.ref,
                "-o",
                str(destination),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return False, f"OCI pull failed: {stderr.decode().strip()}"
            return True, None
        except Exception as e:
            return False, f"OCI pull failed: {e}"

    async def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Checksum verification for OCI is not implemented in v1."""
        return True
