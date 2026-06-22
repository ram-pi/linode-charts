"""
Pydantic models and enums for cache configuration.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, validator


class SourceType(str, Enum):
    """Supported data sources for cache entries."""

    HUGGINGFACE = "huggingface"
    S3 = "s3"
    HTTPS = "https"
    OCI = "oci"


class CacheEntry(BaseModel):
    """Schema for a single cache entry."""

    name: str = Field(..., description="Unique identifier for this asset")
    source: SourceType = Field(..., description="Data source type")
    ref: str = Field(
        ..., description="Source-specific reference (model ID, S3 URI, URL, artifact ref)"
    )
    version: str = Field(..., description="Version or hash for change detection")
    destination: str = Field(..., description="Path relative to cache root (no absolute paths)")
    sha256: Optional[str] = Field(None, description="Expected SHA256 hash (optional verification)")
    credentials_ref: Optional[str] = Field(
        None, description="Kubernetes Secret name for per-asset credentials"
    )

    @validator("destination")
    def validate_destination(cls, v):
        """Ensure destination is relative and doesn't escape cache root."""
        if v.startswith("/"):
            raise ValueError("destination must be relative (no absolute paths)")
        if ".." in v.split("/"):
            raise ValueError("destination cannot contain '..' path traversal")
        return v

    @validator("ref")
    def validate_ref(cls, v, values):
        """Validate ref format based on source type."""
        if "source" not in values:
            return v

        source = values["source"]
        if source == SourceType.HTTPS:
            if not (v.startswith("https://") or v.startswith("http://")):
                raise ValueError("HTTPS ref must start with https:// or http://")
        elif source == SourceType.S3:
            if not v.startswith("s3://"):
                raise ValueError("S3 ref must start with s3://")
        # HuggingFace and OCI refs are more flexible
        return v

    class Config:
        use_enum_values = False


class CacheConfig(BaseModel):
    """Top-level cache configuration."""

    caches: list[CacheEntry] = Field(default_factory=list, description="List of cache entries")

    class Config:
        use_enum_values = False
