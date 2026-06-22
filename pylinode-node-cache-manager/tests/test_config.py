"""Tests for config parsing and validation."""

import pytest

from pylinode_node_cache_manager.config import AppConfig
from pylinode_node_cache_manager.models import CacheEntry, SourceType


@pytest.mark.unit
def test_app_config_defaults():
    """Test that AppConfig has reasonable defaults."""
    config = AppConfig()
    assert config.metrics_port == 8080
    assert config.reconcile_interval_seconds == 900
    assert config.min_free_disk_percent == 10


@pytest.mark.unit
def test_cache_entry_validation_valid():
    """Test valid cache entry creation."""
    entry = CacheEntry(
        name="test-model",
        source=SourceType.HUGGINGFACE,
        ref="org/model",
        version="1.0.0",
        destination="models/test",
    )
    assert entry.name == "test-model"
    assert entry.destination == "models/test"


@pytest.mark.unit
def test_cache_entry_validation_rejects_absolute_path():
    """Test that absolute paths are rejected."""
    with pytest.raises(ValueError, match="relative"):
        CacheEntry(
            name="test-model",
            source=SourceType.HUGGINGFACE,
            ref="org/model",
            version="1.0.0",
            destination="/absolute/path",
        )


@pytest.mark.unit
def test_cache_entry_validation_rejects_path_traversal():
    """Test that path traversal (..) is rejected."""
    with pytest.raises(ValueError, match=".."):
        CacheEntry(
            name="test-model",
            source=SourceType.HUGGINGFACE,
            ref="org/model",
            version="1.0.0",
            destination="models/../../../etc/passwd",
        )


@pytest.mark.unit
def test_https_ref_validation():
    """Test HTTPS URL validation in ref."""
    # Valid HTTPS
    entry = CacheEntry(
        name="test",
        source=SourceType.HTTPS,
        ref="https://example.com/file.tar.gz",
        version="1.0",
        destination="files/test",
    )
    assert entry.ref.startswith("https://")

    # Invalid ref
    with pytest.raises(ValueError, match="https://"):
        CacheEntry(
            name="test",
            source=SourceType.HTTPS,
            ref="ftp://example.com/file",
            version="1.0",
            destination="files/test",
        )
