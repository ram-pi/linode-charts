"""Tests for storage operations and safety boundaries."""

import pytest

from pylinode_node_cache_manager.storage import StorageManager


@pytest.mark.unit
def test_storage_manager_validate_cache_root(mock_cache_root):
    """Test cache root validation."""
    storage = StorageManager(mock_cache_root)
    assert storage.validate_cache_root()
    assert mock_cache_root.exists()


@pytest.mark.unit
def test_storage_manager_destination_safety_boundary(mock_cache_root):
    """Test that destination paths must stay within cache root."""
    storage = StorageManager(mock_cache_root)

    # Valid: relative path
    valid = storage.get_destination_path("models/test")
    assert str(valid).startswith(str(mock_cache_root))

    # Invalid: absolute path outside cache root
    with pytest.raises(ValueError, match="escapes"):
        storage.get_destination_path("../../../etc/passwd")


@pytest.mark.unit
def test_storage_manager_cache_size(mock_cache_root):
    """Test cache size calculation."""
    storage = StorageManager(mock_cache_root)

    # Create test file
    test_file = mock_cache_root / "test.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("x" * 1024)  # 1KB

    size = storage.get_cache_size()
    assert size >= 1024


@pytest.mark.unit
def test_storage_manager_disk_usage(mock_cache_root):
    """Test disk usage stats."""
    storage = StorageManager(mock_cache_root)
    usage = storage.get_disk_usage()

    assert "used" in usage
    assert "free" in usage
    assert "total" in usage
    assert usage["total"] > 0
    assert usage["free"] > 0
