"""
Filesystem operations and utilities for cache management.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages filesystem operations for cache."""

    def __init__(self, cache_root: Path):
        self.cache_root = cache_root.resolve()
        self._logger = logging.getLogger(self.__class__.__name__)

    def validate_cache_root(self) -> bool:
        """
        Validate cache root is writable and accessible.
        Returns True if valid, False otherwise.
        """
        try:
            # Ensure root exists
            self.cache_root.mkdir(parents=True, exist_ok=True)

            # Test write access
            test_file = self.cache_root / ".health-check.tmp"
            test_file.write_text("ok")
            test_file.unlink()

            self._logger.info(f"Cache root validated: {self.cache_root}")
            return True
        except Exception as e:
            self._logger.error(f"Cache root validation failed: {e}")
            return False

    def get_destination_path(self, relative_dest: str) -> Path:
        """
        Get absolute path for a relative destination.
        Validates that destination is within cache root (security boundary).

        Raises ValueError if destination attempts to escape cache root.
        """
        # Normalize and resolve relative to cache root
        abs_path = (self.cache_root / relative_dest).resolve()

        # Security check: ensure path is under cache root
        try:
            abs_path.relative_to(self.cache_root)
        except ValueError:
            raise ValueError(f"Destination {relative_dest} escapes cache root {self.cache_root}")

        return abs_path

    def ensure_parent_directory(self, path: Path) -> None:
        """Ensure parent directory exists for a file path."""
        path.parent.mkdir(parents=True, exist_ok=True)

    def get_cache_size(self) -> int:
        """Get total size of cache directory in bytes."""
        total = 0
        try:
            for entry in self.cache_root.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except Exception as e:
            self._logger.warning(f"Error calculating cache size: {e}")
        return total

    def get_disk_usage(self) -> dict:
        """
        Get disk usage stats for cache root filesystem.
        Returns dict with 'used', 'free', 'total' in bytes.
        """
        try:
            self.cache_root.mkdir(parents=True, exist_ok=True)
            stat = shutil.disk_usage(str(self.cache_root))
            return {
                "used": stat.used,
                "free": stat.free,
                "total": stat.total,
            }
        except Exception as e:
            self._logger.error(f"Error getting disk usage: {e}")
            return {"used": 0, "free": 0, "total": 0}

    def get_free_disk_percent(self) -> int:
        """Get percentage of free disk space (0-100)."""
        usage = self.get_disk_usage()
        if usage["total"] == 0:
            return 0
        return int(100 * usage["free"] / usage["total"])

    async def delete_file(self, path: Path) -> bool:
        """
        Safely delete a file.
        Returns True if deleted, False if not found or error.
        """
        try:
            if path.is_file():
                path.unlink()
                return True
        except Exception as e:
            self._logger.warning(f"Failed to delete {path}: {e}")
        return False

    async def delete_directory(self, path: Path) -> bool:
        """
        Safely delete a directory recursively.
        Returns True if deleted, False if not found or error.
        """
        try:
            if path.is_dir():
                shutil.rmtree(str(path))
                return True
        except Exception as e:
            self._logger.warning(f"Failed to delete directory {path}: {e}")
        return False

    async def cleanup_stale_files(self, max_age_seconds: int = 300) -> int:
        """
        Clean up stale temporary files (.partial, .lock files).
        Returns count of files deleted.
        """
        import time

        deleted_count = 0
        now = time.time()

        try:
            for pattern in ["**/*.partial", "**/*.lock"]:
                for path in self.cache_root.glob(pattern):
                    try:
                        mtime = path.stat().st_mtime
                        age = now - mtime

                        if age > max_age_seconds:
                            if await self.delete_file(path):
                                deleted_count += 1
                                self._logger.info(f"Cleaned stale file: {path}")
                    except Exception as e:
                        self._logger.warning(f"Error checking {path}: {e}")
        except Exception as e:
            self._logger.error(f"Error during stale file cleanup: {e}")

        return deleted_count
