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
    node_name: str
    lease_name: str
    lease_duration_seconds: int
    renew_interval_seconds: int
    poll_interval_seconds: int
    drain_enabled: bool
    apply_changes: bool
    create_namespace_if_missing: bool
    node_selector: dict[str, str]
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
            node_name=os.getenv("MY_NODE_NAME", "").strip(),
            lease_name=os.getenv("LEASE_NAME", "pylinode-vlan-attacher-leader").strip(),
            lease_duration_seconds=int(os.getenv("LEASE_DURATION_SECONDS", "30")),
            renew_interval_seconds=int(os.getenv("RENEW_INTERVAL_SECONDS", "10")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
            drain_enabled=_as_bool(os.getenv("DRAIN_ENABLED", "true"), True),
            apply_changes=_as_bool(os.getenv("APPLY_CHANGES", "false"), False),
            create_namespace_if_missing=_as_bool(os.getenv("CREATE_NAMESPACE_IF_MISSING", "false"), False),
            node_selector=_as_str_dict(os.getenv("NODE_SELECTOR", "")),
            excluded_ips=_as_str_list(os.getenv("EXCLUDED_IPS", "")),
        )


def _as_str_dict(value: str) -> dict[str, str]:
    raw = value.strip()
    if not raw:
        return {}

    result: dict[str, str] = {}
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    for part in parts:
        if "=" not in part:
            raise ValueError(f"Invalid NODE_SELECTOR entry '{part}'. Expected key=value")
        key, val = part.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key or not val:
            raise ValueError(f"Invalid NODE_SELECTOR entry '{part}'. Expected key=value")
        result[key] = val
    return result
