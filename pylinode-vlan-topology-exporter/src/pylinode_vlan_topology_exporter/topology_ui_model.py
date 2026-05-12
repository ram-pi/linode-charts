"""Live topology model built from exporter Prometheus metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from prometheus_client.parser import text_string_to_metric_families


@dataclass(frozen=True)
class Attachment:
    vlan_label: str
    region: str
    linode_id: int
    linode_label: str
    source: str
    ipam_address: str
    config_id: int
    interface_id: int


@dataclass(frozen=True)
class VlanRecord:
    vlan_label: str
    region: str
    reported_linode_count: int
    attached_linode_count: int


def _sample_labels(sample: Any) -> dict[str, str]:
    labels = getattr(sample, "labels", None)
    return labels if isinstance(labels, dict) else {}


def _sample_value(sample: Any) -> float:
    value = getattr(sample, "value", 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_topology_metrics(metrics_text: str) -> dict[str, Any]:
    vlan_regions: dict[str, str] = {}
    reported_counts: dict[tuple[str, str], int] = {}
    attachments_map: dict[tuple[str, int, str], Attachment] = {}
    scrape_success = 0
    scrape_duration_seconds = 0.0
    api_rate_limit_hits_total = 0.0

    for family in text_string_to_metric_families(metrics_text):
        if family.name == "linode_vlan_scrape_success":
            for sample in family.samples:
                scrape_success = int(_sample_value(sample))
        elif family.name == "linode_vlan_scrape_duration_seconds":
            for sample in family.samples:
                scrape_duration_seconds = _sample_value(sample)
        elif family.name == "linode_vlan_api_rate_limit_hits_total":
            for sample in family.samples:
                api_rate_limit_hits_total = _sample_value(sample)
        elif family.name == "linode_vlan_info":
            for sample in family.samples:
                labels = _sample_labels(sample)
                vlan_label = labels.get("vlan_label", "")
                region = labels.get("region", "")
                if vlan_label:
                    vlan_regions[vlan_label] = region
        elif family.name == "linode_vlan_linode_count":
            for sample in family.samples:
                labels = _sample_labels(sample)
                vlan_label = labels.get("vlan_label", "")
                region = labels.get("region", "")
                reported_counts[(vlan_label, region)] = int(_sample_value(sample))
                if vlan_label and vlan_label not in vlan_regions:
                    vlan_regions[vlan_label] = region
        elif family.name == "linode_vlan_attachment":
            for sample in family.samples:
                labels = _sample_labels(sample)
                vlan_label = labels.get("vlan_label", "")
                region = labels.get("region", vlan_regions.get(vlan_label, ""))
                ipam_address = labels.get("ipam_address", "")
                try:
                    linode_id = int(labels.get("linode_id", "0"))
                except ValueError:
                    linode_id = 0

                attachment = Attachment(
                    vlan_label=vlan_label,
                    region=region,
                    linode_id=linode_id,
                    linode_label=labels.get("linode_label", ""),
                    source=labels.get("source", ""),
                    ipam_address=ipam_address,
                    config_id=int(labels.get("config_id", "0") or 0),
                    interface_id=int(labels.get("interface_id", "0") or 0),
                )
                attachments_map[(vlan_label, linode_id, ipam_address)] = attachment

    attachments = sorted(
        attachments_map.values(),
        key=lambda item: (item.vlan_label, item.region, item.linode_label, item.ipam_address),
    )

    attached_by_vlan: dict[tuple[str, str], set[int]] = {}
    for item in attachments:
        key = (item.vlan_label, item.region)
        if key not in attached_by_vlan:
            attached_by_vlan[key] = set()
        attached_by_vlan[key].add(item.linode_id)

    vlan_keys: set[tuple[str, str]] = set(reported_counts.keys()) | set(attached_by_vlan.keys())
    for vlan_label, region in vlan_regions.items():
        vlan_keys.add((vlan_label, region))

    vlans: list[VlanRecord] = []
    for vlan_label, region in vlan_keys:
        vlans.append(
            VlanRecord(
                vlan_label=vlan_label,
                region=region,
                reported_linode_count=reported_counts.get((vlan_label, region), 0),
                attached_linode_count=len(attached_by_vlan.get((vlan_label, region), set())),
            )
        )

    vlans.sort(key=lambda item: (item.vlan_label, item.region))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scrape": {
            "success": scrape_success,
            "duration_seconds": round(scrape_duration_seconds, 3),
            "api_rate_limit_hits_total": api_rate_limit_hits_total,
        },
        "summary": {
            "vlan_count": len(vlans),
            "attachment_count": len(attachments),
            "unique_linode_count": len({item.linode_id for item in attachments}),
        },
        "vlans": [asdict(item) for item in vlans],
        "attachments": [asdict(item) for item in attachments],
    }
