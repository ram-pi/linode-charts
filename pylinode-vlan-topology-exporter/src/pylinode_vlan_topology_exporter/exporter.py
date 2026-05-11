"""Concurrent Linode VLAN topology collector and Prometheus metrics."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
import threading
import time
from typing import Any

from linode_api4 import LinodeClient
from prometheus_client import Counter, Gauge

from .config import Config


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VlanAttachment:
    vlan_label: str
    vlan_region: str
    linode_id: int
    linode_label: str
    config_id: int
    interface_id: int
    source: str
    ipam_address: str


class VlanTopologyExporter:
    """Collects VLAN topology and updates Prometheus metrics."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client = LinodeClient(cfg.linode_token)
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._next_api_slot = 0.0
        self._linode_label_cache: dict[int, str] = {}

        self.metric_scrape_success = Gauge("linode_vlan_scrape_success", "Last scrape success state")
        self.metric_scrape_duration = Gauge("linode_vlan_scrape_duration_seconds", "Last scrape duration in seconds")
        self.metric_api_rate_limit_hits_total = Counter(
            "linode_vlan_api_rate_limit_hits_total",
            "Number of Linode API requests that hit rate limiting",
        )
        self.metric_vlan_info = Gauge(
            "linode_vlan_info",
            "VLAN metadata record",
            ["vlan_label", "region"],
        )
        self.metric_vlan_attachment = Gauge(
            "linode_vlan_attachment",
            "Linode attached to VLAN",
            ["vlan_label", "region", "linode_id", "linode_label", "config_id", "interface_id", "source", "ipam_address"],
        )
        self.metric_vlan_linode_count = Gauge(
            "linode_vlan_linode_count",
            "Number of attached Linodes reported by VLAN list",
            ["vlan_label", "region"],
        )

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            started = time.monotonic()
            success = 0
            try:
                self.collect_once()
                success = 1
            except Exception:  # noqa: BLE001
                LOGGER.exception("vlan topology scrape failed")
            finally:
                self.metric_scrape_success.set(success)
                self.metric_scrape_duration.set(time.monotonic() - started)

            self.stop_event.wait(self.cfg.scrape_interval_seconds)

    def collect_once(self) -> None:
        vlans = self._list_vlans()
        attachments = self._collect_attachments(vlans)
        attachments.extend(self._discover_interface_only_attachments(vlans))
        attachments = self._dedupe_records(attachments)
        self._publish_metrics(vlans, attachments)
        LOGGER.info("scrape complete vlans=%s attachments=%s", len(vlans), len(attachments))

    def _list_vlans(self) -> list[dict[str, Any]]:
        response = self._api_get("/networking/vlans")
        vlans = response.get("data", [])
        for vlan in vlans:
            vlan["region"] = self._normalize_region(vlan.get("region", ""))
        return self._filter_vlans(vlans)

    def _filter_vlans(self, vlans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.cfg.vlan_label_filter:
            return vlans
        return [item for item in vlans if str(item.get("label", "")).startswith(self.cfg.vlan_label_filter)]

    def _collect_attachments(self, vlans: list[dict[str, Any]]) -> list[VlanAttachment]:
        jobs: list[tuple[str, str, int]] = []
        for vlan in vlans:
            label = str(vlan.get("label", ""))
            region = str(vlan.get("region", ""))
            for linode_id in vlan.get("linodes", []):
                jobs.append((label, region, int(linode_id)))

        attachments: list[VlanAttachment] = []
        with ThreadPoolExecutor(max_workers=self.cfg.max_workers) as pool:
            futures = [pool.submit(self._collect_single_linode, label, region, linode_id) for label, region, linode_id in jobs]
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                    attachments.extend(result)
                except Exception:  # noqa: BLE001
                    LOGGER.exception("failed collecting attachment for one Linode")
        return attachments

    def _collect_single_linode(self, vlan_label: str, vlan_region: str, linode_id: int) -> list[VlanAttachment]:
        label = self._linode_label(linode_id)
        records: list[VlanAttachment] = []

        records.extend(self._collect_from_configs(vlan_label, vlan_region, linode_id, label))
        records.extend(self._collect_from_linode_interfaces(vlan_label, vlan_region, linode_id, label))
        return self._dedupe_records(records)

    def _discover_interface_only_attachments(self, vlans: list[dict[str, Any]]) -> list[VlanAttachment]:
        vlan_region_by_label = {str(v.get("label", "")): str(v.get("region", "")) for v in vlans}
        target_labels = {label for label in vlan_region_by_label if label}
        if not target_labels:
            return []

        linodes = []
        for inst in self.client.linode.instances():
            linodes.append((int(inst.id), str(inst.label)))

        found: list[VlanAttachment] = []
        with ThreadPoolExecutor(max_workers=self.cfg.max_workers) as pool:
            futures = [pool.submit(self._collect_interface_only_for_linode, linode_id, label, target_labels, vlan_region_by_label) for linode_id, label in linodes]
            for fut in as_completed(futures):
                try:
                    found.extend(fut.result())
                except Exception:  # noqa: BLE001
                    LOGGER.exception("failed interface-only discovery for one Linode")
        return found

    def _collect_interface_only_for_linode(
        self,
        linode_id: int,
        linode_label: str,
        target_labels: set[str],
        vlan_region_by_label: dict[str, str],
    ) -> list[VlanAttachment]:
        try:
            interfaces_response = self._api_get(f"/linode/instances/{linode_id}/interfaces")
        except Exception:  # noqa: BLE001
            return []
        interfaces = (interfaces_response.get("data") or interfaces_response.get("interfaces") or [])

        records: list[VlanAttachment] = []
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            nested_vlan = interface.get("vlan") or {}
            purpose = interface.get("purpose", "")
            is_vlan = purpose == "vlan" or bool(nested_vlan)
            if not is_vlan:
                continue
            label_value = nested_vlan.get("vlan_label") or interface.get("label")
            if label_value not in target_labels:
                continue
            ipam = nested_vlan.get("ipam_address") or interface.get("ipam_address") or ""
            records.append(
                VlanAttachment(
                    vlan_label=str(label_value),
                    vlan_region=vlan_region_by_label.get(str(label_value), ""),
                    linode_id=linode_id,
                    linode_label=linode_label,
                    config_id=0,
                    interface_id=int(interface.get("id", 0)),
                    source="linode_interface",
                    ipam_address=str(ipam),
                )
            )
        return records

    @staticmethod
    def _dedupe_records(records: list[VlanAttachment]) -> list[VlanAttachment]:
        unique: dict[tuple[str, int, str], VlanAttachment] = {}
        for record in records:
            key = (record.vlan_label, record.linode_id, record.ipam_address)
            existing = unique.get(key)
            if existing is None:
                unique[key] = record
                continue
            if existing.source == "config" and record.source == "linode_interface":
                unique[key] = record
        return list(unique.values())

    def _collect_from_configs(
        self,
        vlan_label: str,
        vlan_region: str,
        linode_id: int,
        linode_label: str,
    ) -> list[VlanAttachment]:
        configs_response = self._api_get(f"/linode/instances/{linode_id}/configs")
        configs = configs_response.get("data", []) or []
        records: list[VlanAttachment] = []
        for config in configs:
            if not isinstance(config, dict):
                continue
            config_id = int(config.get("id", 0))
            interfaces = config.get("interfaces") or []
            for interface in interfaces:
                if not isinstance(interface, dict):
                    continue
                if interface.get("purpose") != "vlan":
                    continue
                if interface.get("label") != vlan_label:
                    continue
                records.append(
                    VlanAttachment(
                        vlan_label=vlan_label,
                        vlan_region=vlan_region,
                        linode_id=linode_id,
                        linode_label=linode_label,
                        config_id=config_id,
                        interface_id=0,
                        source="config",
                        ipam_address=str(interface.get("ipam_address", "")),
                    )
                )
        return records

    def _collect_from_linode_interfaces(
        self,
        vlan_label: str,
        vlan_region: str,
        linode_id: int,
        linode_label: str,
    ) -> list[VlanAttachment]:
        try:
            interfaces_response = self._api_get(f"/linode/instances/{linode_id}/interfaces")
        except Exception:  # noqa: BLE001
            return []

        interfaces = (interfaces_response.get("data") or interfaces_response.get("interfaces") or [])
        records: list[VlanAttachment] = []
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            nested_vlan = interface.get("vlan") or {}
            purpose = interface.get("purpose", "")
            is_vlan = purpose == "vlan" or bool(nested_vlan)
            if not is_vlan:
                continue
            label_value = nested_vlan.get("vlan_label") or interface.get("label")
            if label_value != vlan_label:
                continue

            ipam = nested_vlan.get("ipam_address") or interface.get("ipam_address") or ""
            records.append(
                VlanAttachment(
                    vlan_label=vlan_label,
                    vlan_region=vlan_region,
                    linode_id=linode_id,
                    linode_label=linode_label,
                    config_id=0,
                    interface_id=int(interface.get("id", 0)),
                    source="linode_interface",
                    ipam_address=str(ipam),
                )
            )
        return records

    def _linode_label(self, linode_id: int) -> str:
        with self._lock:
            cached = self._linode_label_cache.get(linode_id)
        if cached:
            return cached

        data = self._api_get(f"/linode/instances/{linode_id}")
        label = str(data.get("label", str(linode_id)))
        with self._lock:
            self._linode_label_cache[linode_id] = label
        return label

    def _publish_metrics(self, vlans: list[dict[str, Any]], attachments: list[VlanAttachment]) -> None:
        self.metric_vlan_info.clear()
        self.metric_vlan_linode_count.clear()
        self.metric_vlan_attachment.clear()

        for vlan in vlans:
            label = str(vlan.get("label", ""))
            region = str(vlan.get("region", ""))
            linode_count = len(vlan.get("linodes", []))
            self.metric_vlan_info.labels(vlan_label=label, region=region).set(1)
            self.metric_vlan_linode_count.labels(vlan_label=label, region=region).set(linode_count)

        for item in attachments:
            self.metric_vlan_attachment.labels(
                vlan_label=item.vlan_label,
                region=item.vlan_region,
                linode_id=str(item.linode_id),
                linode_label=item.linode_label,
                config_id=str(item.config_id),
                interface_id=str(item.interface_id),
                source=item.source,
                ipam_address=item.ipam_address,
            ).set(1)

    def _api_get(self, path: str) -> dict[str, Any]:
        self._wait_for_rate_slot()
        try:
            return self.client.get(path)
        except Exception as exc:  # noqa: BLE001
            if self._is_rate_limited_error(exc):
                self.metric_api_rate_limit_hits_total.inc()
            raise

    @staticmethod
    def _is_rate_limited_error(exc: Exception) -> bool:
        status = getattr(exc, "status", None)
        if status == 429:
            return True

        response = getattr(exc, "response", None)
        if response is not None and getattr(response, "status_code", None) == 429:
            return True

        text = str(exc).lower()
        return "429" in text and "rate" in text

    @staticmethod
    def _normalize_region(region: Any) -> str:
        if isinstance(region, str):
            if ": " in region:
                return region.split(": ", 1)[1]
            return region
        if isinstance(region, dict):
            candidate = region.get("id") or region.get("region") or region.get("label")
            return str(candidate or "")
        candidate = getattr(region, "id", None)
        if candidate:
            return str(candidate)
        text = str(region)
        if ": " in text:
            return text.split(": ", 1)[1]
        return text

    def _wait_for_rate_slot(self) -> None:
        if self.cfg.max_rps <= 0:
            return
        min_interval = 1.0 / self.cfg.max_rps
        while True:
            with self._rate_lock:
                now = time.monotonic()
                wait_for = self._next_api_slot - now
                if wait_for <= 0:
                    self._next_api_slot = now + min_interval
                    return
            time.sleep(min(wait_for, 0.05))
