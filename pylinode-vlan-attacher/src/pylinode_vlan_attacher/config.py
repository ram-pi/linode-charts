"""Runtime configuration from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _as_bool(value: str, default: bool) -> bool:
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _as_str_list(value: str) -> list[str]:
    raw = value.replace(",", " ").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split() if item.strip()]


@dataclass(frozen=True)
class Config:
    linode_token: str
    vlan_name: str
    vlan_cidr: str
    namespace: str
    pod_name: str
    lease_name: str
    lease_duration_seconds: int
    renew_interval_seconds: int
    poll_interval_seconds: int
    drain_enabled: bool
    apply_changes: bool
    excluded_ips: list[str]

    @classmethod
    def from_env(cls) -> "Config":
        default_pod_name = f"local-dev-{os.getpid()}"
        return cls(
            linode_token=_required("LINODE_TOKEN"),
            vlan_name=_required("VLAN_NAME"),
            vlan_cidr=_required("VLAN_CIDR"),
            namespace=os.getenv("MY_NAMESPACE", "default").strip(),
            pod_name=os.getenv("MY_POD_NAME", default_pod_name).strip(),
            lease_name=os.getenv("LEASE_NAME", "pylinode-vlan-attacher-leader").strip(),
            lease_duration_seconds=int(os.getenv("LEASE_DURATION_SECONDS", "30")),
            renew_interval_seconds=int(os.getenv("RENEW_INTERVAL_SECONDS", "10")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
            drain_enabled=_as_bool(os.getenv("DRAIN_ENABLED", "true"), True),
            apply_changes=_as_bool(os.getenv("APPLY_CHANGES", "false"), False),
            excluded_ips=_as_str_list(os.getenv("EXCLUDED_IPS", "")),
        )
