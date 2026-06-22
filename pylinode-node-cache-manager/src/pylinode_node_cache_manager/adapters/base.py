"""
Abstract base class for download adapters.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Callable, Awaitable

from ..models import CacheEntry, SourceType


class DownloadAdapter(ABC):
    """Abstract adapter for downloading cache assets."""

    @abstractmethod
    async def download(
        self,
        entry: CacheEntry,
        destination: Path,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Download a cache entry to destination.

        Args:
            entry: Cache entry to download
            destination: Local file/directory path
            progress_callback: Optional async callback for progress updates

        Returns:
            (success, error_message): True if successful, False with error message on failure
        """
        pass

    @abstractmethod
    async def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Verify SHA256 checksum of downloaded file."""
        pass


class DownloadManager:
    """Manages downloads using appropriate adapters."""

    def __init__(self, adapters: dict[SourceType, DownloadAdapter]):
        self.adapters = adapters

    async def download(
        self,
        entry: CacheEntry,
        destination: Path,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Download using the appropriate adapter for the source type."""
        adapter = self.adapters.get(entry.source)
        if not adapter:
            return False, f"No adapter for source type: {entry.source}"

        return await adapter.download(entry, destination, progress_callback)
