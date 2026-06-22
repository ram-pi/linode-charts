"""
Cache reconciliation and garbage collection manager.
"""

import json
import logging
import os
from pathlib import Path
import re
from typing import Optional

from prometheus_client import Counter, Gauge

from .models import CacheConfig, SourceType
from .storage import StorageManager
from .adapters.base import DownloadManager
from .adapters.implementations import (
    HuggingFaceAdapter,
    S3Adapter,
    HTTPSAdapter,
    OCIAdapter,
)

logger = logging.getLogger(__name__)

# Prometheus metrics
cache_download_success = Counter(
    "cache_download_success_total",
    "Successful cache downloads",
    ["source", "asset"],
)
cache_download_failure = Counter(
    "cache_download_failure_total",
    "Failed cache downloads",
    ["source", "asset", "reason"],
)
cache_download_bytes = Counter(
    "cache_download_bytes_total",
    "Total bytes downloaded",
    ["asset"],
)
cache_gc_runs = Counter(
    "cache_gc_runs_total",
    "Total GC cycles",
)
cache_gc_bytes_freed = Counter(
    "cache_gc_bytes_freed_total",
    "Bytes freed by GC",
)
cache_gc_failures = Counter(
    "cache_gc_failures_total",
    "GC cycle failures",
)
node_disk_used = Gauge(
    "node_disk_used_bytes",
    "Used disk space",
)
node_disk_free = Gauge(
    "node_disk_free_bytes",
    "Free disk space",
)
cache_size = Gauge(
    "cache_size_bytes",
    "Total cache size",
)
node_disk_used_mb = Gauge(
    "node_disk_used_megabytes",
    "Used disk space in megabytes",
)
node_disk_free_mb = Gauge(
    "node_disk_free_megabytes",
    "Free disk space in megabytes",
)
cache_size_mb = Gauge(
    "cache_size_megabytes",
    "Total cache size in megabytes",
)
node_disk_used_gb = Gauge(
    "node_disk_used_gigabytes",
    "Used disk space in gigabytes",
)
node_disk_free_gb = Gauge(
    "node_disk_free_gigabytes",
    "Free disk space in gigabytes",
)
cache_size_gb = Gauge(
    "cache_size_gigabytes",
    "Total cache size in gigabytes",
)
cache_asset_declared = Gauge(
    "cache_asset_declared",
    "Configured cache asset metadata (always 1 for declared assets)",
    ["asset", "source", "ref", "version", "destination"],
)
cache_asset_present = Gauge(
    "cache_asset_present",
    "Whether configured asset destination currently exists on disk (1 or 0)",
    ["asset", "destination"],
)
cache_asset_size_bytes = Gauge(
    "cache_asset_size_bytes",
    "Current on-disk size in bytes for configured asset destination",
    ["asset", "destination"],
)


def _path_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        total = 0
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total
    return 0


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _set_storage_metrics(
    used_bytes: int, free_bytes: int, total_bytes: int, cache_bytes: int
) -> None:
    """Populate byte, MB, and GB storage metrics."""
    node_disk_used.set(used_bytes)
    node_disk_free.set(free_bytes)
    cache_size.set(cache_bytes)

    node_disk_used_mb.set(used_bytes / 1024 / 1024)
    node_disk_free_mb.set(free_bytes / 1024 / 1024)
    cache_size_mb.set(cache_bytes / 1024 / 1024)

    node_disk_used_gb.set(used_bytes / 1024 / 1024 / 1024)
    node_disk_free_gb.set(free_bytes / 1024 / 1024 / 1024)
    cache_size_gb.set(cache_bytes / 1024 / 1024 / 1024)


class CacheManager:
    """Manages cache reconciliation, downloads, and garbage collection."""

    def __init__(
        self,
        cache_root: Path,
        manifest: CacheConfig,
        download_timeout: int = 3600,
        min_free_disk_percent: int = 10,
        hf_token: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        self.cache_root = cache_root
        self.manifest = manifest
        self.download_timeout = download_timeout
        self.min_free_disk_percent = min_free_disk_percent

        self.storage = StorageManager(cache_root)

        # Initialize download adapters
        adapters = {
            SourceType.HUGGINGFACE: HuggingFaceAdapter(token=hf_token),
            SourceType.S3: S3Adapter(
                access_key=aws_access_key_id, secret_key=aws_secret_access_key
            ),
            SourceType.HTTPS: HTTPSAdapter(timeout=download_timeout),
            SourceType.OCI: OCIAdapter(),
        }
        self.download_manager = DownloadManager(adapters)
        self._state_file = self.cache_root / ".managed_paths.json"
        self._declared_metric_labels: set[tuple[str, str, str, str, str]] = set()
        self._status_metric_labels: set[tuple[str, str]] = set()

        self._logger = logging.getLogger(self.__class__.__name__)

    def _update_asset_inventory_metrics(self) -> None:
        """Publish per-asset inventory metrics and clear stale label sets."""
        current_declared: set[tuple[str, str, str, str, str]] = set()
        current_status: set[tuple[str, str]] = set()

        for entry in self.manifest.caches:
            declared_labels = (
                entry.name,
                entry.source.value,
                entry.ref,
                entry.version,
                entry.destination,
            )
            current_declared.add(declared_labels)
            cache_asset_declared.labels(*declared_labels).set(1)

            status_labels = (entry.name, entry.destination)
            current_status.add(status_labels)

            destination = self.storage.get_destination_path(entry.destination)
            if destination.exists():
                size_bytes = _path_size_bytes(destination)
                cache_asset_present.labels(*status_labels).set(1)
                cache_asset_size_bytes.labels(*status_labels).set(size_bytes)
            else:
                cache_asset_present.labels(*status_labels).set(0)
                cache_asset_size_bytes.labels(*status_labels).set(0)

        for labels in self._declared_metric_labels - current_declared:
            cache_asset_declared.remove(*labels)

        stale_status = self._status_metric_labels - current_status
        for labels in stale_status:
            cache_asset_present.remove(*labels)
            cache_asset_size_bytes.remove(*labels)

        self._declared_metric_labels = current_declared
        self._status_metric_labels = current_status

    @staticmethod
    def _normalize_credentials_ref(credentials_ref: str) -> str:
        """Normalize credentials_ref to uppercase env-safe token."""
        normalized = re.sub(r"[^A-Za-z0-9]", "_", credentials_ref).upper()
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized

    def _apply_asset_credentials(self, credentials_ref: Optional[str]) -> dict[str, Optional[str]]:
        """Apply per-asset credential env vars and return previous values for restore."""
        tracked_env = [
            "HF_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "HTTPS_BEARER_TOKEN",
        ]
        previous = {k: os.environ.get(k) for k in tracked_env}

        if not credentials_ref:
            return previous

        ref = self._normalize_credentials_ref(credentials_ref)
        mapping = {
            f"CREDENTIALS_{ref}_HF_TOKEN": "HF_TOKEN",
            f"CREDENTIALS_{ref}_AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID",
            f"CREDENTIALS_{ref}_AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY",
            f"CREDENTIALS_{ref}_AWS_SESSION_TOKEN": "AWS_SESSION_TOKEN",
            f"CREDENTIALS_{ref}_HTTPS_BEARER_TOKEN": "HTTPS_BEARER_TOKEN",
        }

        for source_key, target_key in mapping.items():
            value = os.environ.get(source_key)
            if value:
                os.environ[target_key] = value

        return previous

    @staticmethod
    def _restore_asset_credentials(previous: dict[str, Optional[str]]) -> None:
        """Restore credential env vars after an asset download."""
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _log_storage_status(self, label: str = "") -> None:
        """Log a human-readable storage summary line."""
        usage = self.storage.get_disk_usage()
        cache_bytes = self.storage.get_cache_size()
        free_pct = int(100 * usage["free"] / usage["total"]) if usage["total"] > 0 else 0
        prefix = f"[{label}] " if label else ""
        self._logger.info(
            f"{prefix}Storage: cache={_human_bytes(cache_bytes)}"
            f" | free={_human_bytes(usage['free'])} ({free_pct}%)"
            f" | used={_human_bytes(usage['used'])}"
            f" | total={_human_bytes(usage['total'])}"
        )

    async def reconcile(self) -> None:
        """
        Main reconciliation loop: ensure cache state matches manifest.

        1. Validate cache root
        2. Pre-download disk space check
        3. Download missing/updated assets
        4. Run garbage collection
        5. Update metrics
        """
        self._logger.info("Starting reconciliation")

        try:
            # Validate cache root
            if not self.storage.validate_cache_root():
                self._logger.error("Cache root validation failed")
                return

            if not self.manifest.caches:
                self._update_asset_inventory_metrics()
                self._logger.info("No cache entries configured")
                return

            # Log + update metrics before downloads
            self._log_storage_status("before")
            usage = self.storage.get_disk_usage()
            _set_storage_metrics(
                usage["used"], usage["free"], usage["total"], self.storage.get_cache_size()
            )

            desired_paths: list[str] = []

            for entry in self.manifest.caches:
                destination = self.storage.get_destination_path(entry.destination)
                desired_paths.append(str(destination))

                # Skip when already present for v1.
                if destination.exists():
                    self._logger.info(
                        "Asset already present; skipping download",
                        extra={"asset": entry.name, "destination": str(destination)},
                    )
                    continue

                free_percent = self.storage.get_free_disk_percent()
                if free_percent < self.min_free_disk_percent:
                    reason = "insufficient_disk_space"
                    self._logger.warning(
                        "Skipping download due to low free disk",
                        extra={
                            "asset": entry.name,
                            "free_percent": free_percent,
                            "required_percent": self.min_free_disk_percent,
                        },
                    )
                    cache_download_failure.labels(entry.source.value, entry.name, reason).inc()
                    continue

                self._logger.info(
                    "Downloading asset",
                    extra={
                        "asset": entry.name,
                        "source": entry.source.value,
                        "destination": str(destination),
                    },
                )
                previous_creds = self._apply_asset_credentials(entry.credentials_ref)
                try:
                    success, error = await self.download_manager.download(entry, destination)
                finally:
                    self._restore_asset_credentials(previous_creds)
                if success:
                    downloaded_size = _path_size_bytes(destination)
                    cache_download_success.labels(entry.source.value, entry.name).inc()
                    if downloaded_size > 0:
                        cache_download_bytes.labels(entry.name).inc(downloaded_size)
                    self._logger.info(
                        "Asset download complete",
                        extra={"asset": entry.name, "bytes": downloaded_size},
                    )
                else:
                    reason = (error or "download_error").replace(" ", "_")[:80]
                    cache_download_failure.labels(entry.source.value, entry.name, reason).inc()
                    self._logger.error(f"Asset download failed: {entry.name}: {error}")

            await self._run_gc(desired_paths)

            # Refresh metrics + log summary after reconcile/GC
            usage = self.storage.get_disk_usage()
            _set_storage_metrics(
                usage["used"], usage["free"], usage["total"], self.storage.get_cache_size()
            )
            self._update_asset_inventory_metrics()
            self._log_storage_status("after")

            self._logger.info("Reconciliation complete")
        except Exception as e:
            self._logger.error(f"Reconciliation failed: {e}", exc_info=True)

    async def _run_gc(self, desired_paths: list[str]) -> None:
        """Remove managed paths that are no longer desired, constrained to cache root."""
        cache_gc_runs.inc()

        previous_paths: list[str] = []
        if self._state_file.exists():
            try:
                previous_paths = json.loads(self._state_file.read_text())
            except Exception:
                previous_paths = []

        desired_set = set(desired_paths)
        stale_paths = [p for p in previous_paths if p not in desired_set]
        bytes_freed = 0

        for stale in stale_paths:
            try:
                stale_path = Path(stale).resolve()
                stale_path.relative_to(self.cache_root.resolve())
            except Exception:
                self._logger.warning(f"Skipping unsafe stale path outside cache root: {stale}")
                continue

            if not stale_path.exists():
                continue

            size_before = _path_size_bytes(stale_path)
            deleted = False
            if stale_path.is_file():
                deleted = await self.storage.delete_file(stale_path)
            elif stale_path.is_dir():
                deleted = await self.storage.delete_directory(stale_path)

            if deleted:
                bytes_freed += size_before
                self._logger.info(f"GC removed stale path: {stale_path}")

        if bytes_freed > 0:
            cache_gc_bytes_freed.inc(bytes_freed)

        try:
            self._state_file.write_text(json.dumps(desired_paths, indent=2))
        except Exception as e:
            cache_gc_failures.inc()
            self._logger.error(f"Failed to persist GC state file: {e}")

    async def cleanup(self) -> None:
        """Cleanup on daemon shutdown."""
        self._logger.info("CacheManager cleanup")
        # TODO: Cancel any in-flight downloads
