"""Runtime configuration for VLAN topology exporter."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    linode_token: str
    scrape_interval_seconds: int
    listen_port: int
    max_workers: int
    max_rps: float
    vlan_label_filter: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            linode_token=_required("LINODE_TOKEN"),
            scrape_interval_seconds=int(os.getenv("SCRAPE_INTERVAL_SECONDS", "60")),
            listen_port=int(os.getenv("METRICS_PORT", "9108")),
            max_workers=int(os.getenv("MAX_WORKERS", "32")),
            max_rps=float(os.getenv("MAX_RPS", "15")),
            vlan_label_filter=os.getenv("VLAN_LABEL_FILTER", "").strip(),
        )
