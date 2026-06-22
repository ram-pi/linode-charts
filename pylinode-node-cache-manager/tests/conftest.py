"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def mock_cache_root(tmp_path):
    """Temporary cache directory for testing."""
    return tmp_path / "cache"


@pytest.fixture
def mock_config(mock_cache_root):
    """Mock configuration for testing."""
    from pylinode_node_cache_manager.config import AppConfig

    config = AppConfig()
    config.cache_path = str(mock_cache_root)
    return config
