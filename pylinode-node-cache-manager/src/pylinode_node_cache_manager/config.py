"""
Environment configuration parsing for node cache manager.
Follows patterns from pylinode-vlan-attacher.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

from .models import CacheConfig

logger = logging.getLogger(__name__)


def _required(name: str) -> str:
    """Get required environment variable; fail fast if missing."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Required environment variable missing: {name}")
    return value


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean from env var."""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def _as_str_list(value: Optional[str], sep: str = " ") -> list[str]:
    """Parse space or comma-separated list from env var."""
    if not value:
        return []
    return [v.strip() for v in value.split(sep) if v.strip()]


def _as_int(value: Optional[str], default: int) -> int:
    """Parse integer from env var."""
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class AppConfig(BaseSettings):
    """Application configuration from environment variables."""

    # Required
    cache_path: str = _required("CACHE_PATH") if "CACHE_PATH" in os.environ else "/opt/node-cache"

    # Optional with defaults
    metrics_port: int = int(os.getenv("METRICS_PORT", "8080"))
    reconcile_interval_seconds: int = int(os.getenv("RECONCILE_INTERVAL_SECONDS", "900"))
    min_free_disk_percent: int = int(os.getenv("MIN_FREE_DISK_PERCENT", "10"))
    download_timeout_seconds: int = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "3600"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Credentials (optional, from Kubernetes Secrets or env)
    hf_token: Optional[str] = os.getenv("HF_TOKEN")
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")

    class Config:
        case_sensitive = False
        env_file = ".env"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load config from environment variables."""
        return cls()

    def validate(self) -> None:
        """Validate critical config values."""
        if not self.cache_path:
            raise ValueError("cache_path is required")
        if self.metrics_port <= 0 or self.metrics_port > 65535:
            raise ValueError(f"Invalid metrics_port: {self.metrics_port}")
        if self.min_free_disk_percent < 0 or self.min_free_disk_percent > 100:
            raise ValueError(
                f"min_free_disk_percent must be 0-100, got {self.min_free_disk_percent}"
            )
        if self.reconcile_interval_seconds <= 0:
            raise ValueError(
                f"reconcile_interval_seconds must be positive, got {self.reconcile_interval_seconds}"
            )

        # Ensure cache path exists or is creatable
        cache_dir = Path(self.cache_path)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(f"Cannot create cache path {self.cache_path}: {e}")


def load_cache_manifest(assets_json_str: Optional[str] = None) -> CacheConfig:
    """
    Load cache manifest from environment variable or file.

    Try to load from:
    1. ASSETS_JSON env var (JSON string)
    2. ASSETS_FILE env var (path to JSON file)
    3. Return empty CacheConfig if neither provided
    """
    if not assets_json_str:
        assets_json_str = os.getenv("ASSETS_JSON")

    if not assets_json_str:
        assets_file = os.getenv("ASSETS_FILE")
        if assets_file:
            try:
                with open(assets_file) as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load ASSETS_FILE {assets_file}: {e}")
                return CacheConfig()
        else:
            logger.info("No ASSETS_JSON or ASSETS_FILE provided; starting with empty cache")
            return CacheConfig()
    else:
        try:
            data = json.loads(assets_json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ASSETS_JSON: {e}")
            return CacheConfig()

    # Parse the data into CacheConfig
    try:
        if isinstance(data, list):
            config = CacheConfig(caches=data)
        elif isinstance(data, dict):
            config = CacheConfig(**data)
        else:
            logger.error(f"Unexpected assets data type: {type(data)}")
            return CacheConfig()

        logger.info(f"Loaded {len(config.caches)} cache entries")
        return config
    except Exception as e:
        logger.error(f"Failed to validate cache manifest: {e}")
        return CacheConfig()
