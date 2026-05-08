"""Controller loop with leader/standby behavior."""

from __future__ import annotations

from ipaddress import ip_address, ip_network
import logging
import threading
import time
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from .config import Config
from .lease import LeaseManager
from .linode_api import LinodeAPI


LOGGER = logging.getLogger(__name__)


class VLANAttacherController:
    """Leader-elected controller for VLAN attachment workflows."""

    def __init__(self, cfg: Config, stop_event: threading.Event | None = None) -> None:
        self.cfg = cfg
        self.stop_event = stop_event or threading.Event()
        self._load_kube_config()
        self.core = client.CoreV1Api()
        self.coord = client.CoordinationV1Api()
        self._ensure_namespace_exists()
        self.linode = LinodeAPI(cfg.linode_token)
        self.lease = LeaseManager(
            api=self.coord,
            namespace=cfg.namespace,
            lease_name=cfg.lease_name,
            holder_identity=cfg.pod_name,
            lease_duration_seconds=cfg.lease_duration_seconds,
        )

    @staticmethod
    def _load_kube_config() -> None:
        try:
            config.load_incluster_config()
            return
        except config.ConfigException:
            pass
        config.load_kube_config()

    def run(self) -> None:
        _ = ip_network(self.cfg.vlan_cidr, strict=False)
        LOGGER.info("starting controller pod=%s lease=%s", self.cfg.pod_name, self.cfg.lease_name)
        if not self.cfg.apply_changes:
            LOGGER.warning("APPLY_CHANGES=false: running in observe-only mode (no Linode or node mutations)")
        last_mode = ""
        while not self.stop_event.is_set():
            try:
                have_lease = self.lease.try_acquire_or_renew()
            except Exception:  # noqa: BLE001
                LOGGER.exception("lease check failed")
                self._sleep_with_stop(self.cfg.renew_interval_seconds)
                continue

            if have_lease:
                if last_mode != "leader":
                    LOGGER.info("leader mode: lease acquired by %s", self.cfg.pod_name)
                    last_mode = "leader"
                self._leader_loop()
                continue

            if last_mode != "standby":
                holder = "unknown"
                try:
                    holder = self.lease.current_holder() or "<none>"
                except Exception:  # noqa: BLE001
                    LOGGER.exception("failed to read current lease holder")
                LOGGER.info(
                    "standby mode: lease currently held by %s. "
                    "This instance will take over only after lease expiry.",
                    holder,
                )
                last_mode = "standby"
            self._sleep_with_stop(self.cfg.renew_interval_seconds)

        LOGGER.info("shutdown requested, exiting controller")

    def _ensure_namespace_exists(self) -> None:
        try:
            self.core.read_namespace(self.cfg.namespace)
        except ApiException as exc:
            if exc.status == 404:
                if self.cfg.create_namespace_if_missing:
                    LOGGER.info("namespace %s not found, creating it", self.cfg.namespace)
                    body = client.V1Namespace(metadata=client.V1ObjectMeta(name=self.cfg.namespace))
                    self.core.create_namespace(body)
                    return
                raise RuntimeError(
                    f"Namespace '{self.cfg.namespace}' not found. "
                    f"Create it first: kubectl create namespace {self.cfg.namespace} "
                    f"or set CREATE_NAMESPACE_IF_MISSING=true"
                ) from exc
            raise

    def _leader_loop(self) -> None:
        while not self.stop_event.is_set():
            if not self.lease.try_acquire_or_renew():
                LOGGER.info("lease lost, moving to standby mode")
                return
            try:
                self.reconcile_once()
            except Exception:  # noqa: BLE001
                LOGGER.exception("reconcile iteration failed")
            self._sleep_with_stop(self.cfg.poll_interval_seconds)

    def reconcile_once(self) -> None:
        nodes = self._k8s_nodes()
        linodes = self.linode.list_lke_nodes()
        vlan_nodes = self._vlan_linode_ids()
        used_ips = self._used_vlan_ips(vlan_nodes)
        used_ips.update(self.cfg.excluded_ips)
        cidr = ip_network(self.cfg.vlan_cidr, strict=False)
        prefix = cidr.prefixlen

        if self.cfg.excluded_ips:
            LOGGER.info("excluded IPs configured count=%s", len(self.cfg.excluded_ips))
            for excluded in self.cfg.excluded_ips:
                if ip_address(excluded) not in cidr:
                    LOGGER.warning("excluded IP %s is outside VLAN_CIDR %s", excluded, self.cfg.vlan_cidr)

        pending: list[dict[str, Any]] = []
        for node_name in nodes:
            match = next((l for l in linodes if l["label"] == node_name), None)
            if not match:
                LOGGER.warning("no Linode found for node=%s", node_name)
                continue
            configs = self.linode.configs_list(int(match["id"]))
            if not configs:
                LOGGER.warning("no config found for node=%s linode=%s", node_name, match["id"])
                continue
            config0 = configs[0]
            if not self._has_vlan(config0, self.cfg.vlan_name):
                pending.append({"node": node_name, "linode_id": int(match["id"]), "config_id": int(config0["id"]), "config": config0})

        LOGGER.info(
            "reconcile complete: nodes=%s vlan_known_linode_ids=%s pending_vlan_attach=%s apply_changes=%s",
            len(nodes),
            len(vlan_nodes),
            len(pending),
            self.cfg.apply_changes,
        )

        if not pending:
            LOGGER.info("no pending nodes require VLAN attachment")
            return

        if not self.cfg.apply_changes and pending:
            sample = ", ".join(f"{p['node']}:{p['linode_id']}" for p in pending[:3])
            LOGGER.info("observe-only pending sample: %s", sample)
            return

        for candidate in pending:
            if not self.lease.try_acquire_or_renew():
                LOGGER.info("lease lost before applying changes")
                return
            node_name = str(candidate["node"])
            linode_id = int(candidate["linode_id"])
            config_id = int(candidate["config_id"])
            config_data = dict(candidate["config"])

            if not self._cluster_all_ready(excluding=node_name):
                LOGGER.warning("cluster not healthy enough to cycle node=%s, deferring", node_name)
                self._log_cluster_readiness(excluding=node_name)
                return

            next_ip = self._next_available_ip(cidr, used_ips)
            if next_ip is None:
                raise RuntimeError(f"No available IP left in {self.cfg.vlan_cidr}")
            used_ips.add(next_ip)
            ipam = f"{next_ip}/{prefix}"

            LOGGER.info("attaching vlan to node=%s linode=%s ipam=%s", node_name, linode_id, ipam)
            self._label_node(node_name, "lke-vlan-controller-status", "pending_reboot")
            self._cordon(node_name, True)

            payload = self._build_updated_config(config_data, ipam)
            LOGGER.info("node=%s using unified flow (shutdown -> update -> boot)", node_name)
            self.linode.shutdown(linode_id)
            self._wait_linode_status(linode_id, "offline", timeout_seconds=300)
            self.linode.config_update(linode_id, config_id, payload)
            self.linode.boot(linode_id)

            self._wait_node_not_ready(node_name, timeout_seconds=180)
            self._wait_node_ready(node_name, timeout_seconds=600)

            self._label_node(node_name, "vlan-ip", ipam.replace("/", "_"))
            self._label_node(node_name, "lke-vlan-controller-status", "completed")
            self._cordon(node_name, False)
            LOGGER.info("node=%s completed vlan attach", node_name)

    def _k8s_nodes(self) -> list[str]:
        data = self.core.list_node()
        selected: list[str] = []
        for item in data.items:
            if not item.metadata or not item.metadata.name:
                continue
            labels = item.metadata.labels or {}
            if self.cfg.node_selector and not self._labels_match_selector(labels):
                continue
            selected.append(item.metadata.name)
        if self.cfg.node_selector:
            LOGGER.info("node selector=%s matched nodes=%s", self.cfg.node_selector, len(selected))
        return selected

    def _labels_match_selector(self, labels: dict[str, str]) -> bool:
        for key, expected in self.cfg.node_selector.items():
            if labels.get(key) != expected:
                return False
        return True

    def _vlan_linode_ids(self) -> set[int]:
        ids: set[int] = set()
        vlans = self.linode.list_vlans()
        LOGGER.info("discovered vlan objects=%s", len(vlans))
        for vlan in vlans:
            if vlan.get("label") != self.cfg.vlan_name:
                continue
            for linode_id in vlan.get("linodes", []):
                ids.add(int(linode_id))
        return ids

    def _used_vlan_ips(self, vlan_linode_ids: set[int]) -> set[str]:
        used: set[str] = set()
        for linode_id in vlan_linode_ids:
            for conf in self.linode.configs_list(linode_id):
                for iface in conf.get("interfaces", []):
                    if iface.get("purpose") != "vlan":
                        continue
                    if iface.get("label") != self.cfg.vlan_name:
                        continue
                    ipam = str(iface.get("ipam_address", ""))
                    if not ipam:
                        continue
                    used.add(ipam.split("/")[0])
        return used

    @staticmethod
    def _next_available_ip(cidr: Any, used_ips: set[str]) -> str | None:
        for host in cidr.hosts():
            candidate = str(host)
            if candidate in used_ips:
                continue
            return candidate
        return None

    def _label_node(self, node_name: str, key: str, value: str) -> None:
        body = {"metadata": {"labels": {key: value}}}
        self.core.patch_node(node_name, body)

    def _cordon(self, node_name: str, unschedulable: bool) -> None:
        body = {"spec": {"unschedulable": unschedulable}}
        self.core.patch_node(node_name, body)

    def _is_node_ready(self, node_name: str) -> bool:
        node = self.core.read_node(node_name)
        conditions = node.status.conditions or []
        for condition in conditions:
            if condition.type == "Ready":
                return condition.status == "True"
        return False

    def _wait_node_ready(self, node_name: str, timeout_seconds: int) -> None:
        elapsed = 0
        interval = 15
        while elapsed < timeout_seconds:
            if self.stop_event.is_set():
                raise RuntimeError("Shutdown requested while waiting for node readiness")
            if not self.lease.try_acquire_or_renew():
                raise RuntimeError("Lost leader lease while waiting for node readiness")
            if self._is_node_ready(node_name):
                LOGGER.info("node=%s is Ready", node_name)
                return
            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"Node {node_name} did not become Ready within {timeout_seconds}s")

    def _wait_node_not_ready(self, node_name: str, timeout_seconds: int) -> None:
        elapsed = 0
        interval = 10
        while elapsed < timeout_seconds:
            if self.stop_event.is_set():
                raise RuntimeError("Shutdown requested while waiting for node NotReady")
            if not self.lease.try_acquire_or_renew():
                raise RuntimeError("Lost leader lease while waiting for node NotReady")
            if not self._is_node_ready(node_name):
                LOGGER.info("node=%s is NotReady", node_name)
                return
            time.sleep(interval)
            elapsed += interval
        LOGGER.warning("node=%s did not transition to NotReady within %ss", node_name, timeout_seconds)

    def _wait_linode_status(self, linode_id: int, desired_status: str, timeout_seconds: int) -> None:
        elapsed = 0
        interval = 10
        while elapsed < timeout_seconds:
            if self.stop_event.is_set():
                raise RuntimeError("Shutdown requested while waiting for Linode status")
            if not self.lease.try_acquire_or_renew():
                raise RuntimeError("Lost leader lease while waiting for Linode status")
            status = self.linode.status(linode_id)
            if status == desired_status:
                return
            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"Linode {linode_id} did not reach status {desired_status} in {timeout_seconds}s")

    def _cluster_all_ready(self, excluding: str) -> bool:
        data = self.core.list_node()
        for node in data.items:
            if not node.metadata or not node.metadata.name:
                continue
            if node.metadata.name == excluding:
                continue
            if getattr(node.spec, "unschedulable", False):
                return False
            conditions = node.status.conditions or []
            ready = next((c for c in conditions if c.type == "Ready"), None)
            if ready is None or ready.status != "True":
                return False
        return True

    def _log_cluster_readiness(self, excluding: str) -> None:
        data = self.core.list_node()
        for node in data.items:
            if not node.metadata or not node.metadata.name:
                continue
            node_name = node.metadata.name
            if node_name == excluding:
                continue
            unschedulable = bool(getattr(node.spec, "unschedulable", False))
            conditions = node.status.conditions or []
            ready = next((c for c in conditions if c.type == "Ready"), None)
            ready_value = ready.status if ready is not None else "Unknown"
            LOGGER.info(
                "cluster node status: node=%s ready=%s unschedulable=%s",
                node_name,
                ready_value,
                unschedulable,
            )

    def _build_updated_config(self, current: dict[str, Any], ipam: str) -> dict[str, Any]:
        interfaces: list[dict[str, Any]] = []
        for interface in current.get("interfaces", []):
            if interface.get("purpose") == "vlan" and interface.get("label") == self.cfg.vlan_name:
                continue
            cleaned = {k: v for k, v in interface.items() if k not in {"id", "active", "vpc_id"}}
            if cleaned.get("purpose") == "vpc" and isinstance(cleaned.get("ipv6"), dict):
                cleaned["ipv6"]["is_public"] = True
            interfaces.append(cleaned)

        has_public = any(iface.get("purpose") == "public" for iface in interfaces)
        has_vpc = any(iface.get("purpose") == "vpc" for iface in interfaces)
        if not has_public and not has_vpc:
            interfaces.insert(0, {"purpose": "public"})

        interfaces.append({"purpose": "vlan", "label": self.cfg.vlan_name, "ipam_address": ipam})
        return {
            "kernel": current.get("kernel"),
            "run_level": current.get("run_level"),
            "virt_mode": current.get("virt_mode"),
            "root_device": current.get("root_device"),
            "helpers": current.get("helpers"),
            "devices": current.get("devices"),
            "memory_limit": current.get("memory_limit"),
            "comments": current.get("comments", ""),
            "interfaces": interfaces,
        }

    def _sleep_with_stop(self, seconds: int) -> None:
        self.stop_event.wait(timeout=max(1, seconds))

    @staticmethod
    def _has_vlan(config: dict[str, Any], vlan_name: str) -> bool:
        for iface in config.get("interfaces", []):
            if iface.get("purpose") == "vlan" and iface.get("label") == vlan_name:
                return True
        return False
