"""Linode API helpers using linode_api4 client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from linode_api4 import LinodeClient


@dataclass
class LinodeAPI:
    token: str

    def __post_init__(self) -> None:
        self.client = LinodeClient(self.token)

    def list_lke_nodes(self) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for inst in self.client.linode.instances():
            nodes.append({"id": inst.id, "label": inst.label, "status": getattr(inst, "status", "")})
        return nodes

    def list_vlans(self) -> list[dict[str, Any]]:
        networking = getattr(self.client, "networking", None)
        if networking and hasattr(networking, "vlans"):
            result: list[dict[str, Any]] = []
            for vlan in networking.vlans():
                result.append(
                    {
                        "id": getattr(vlan, "id", None),
                        "label": getattr(vlan, "label", None),
                        "linodes": list(getattr(vlan, "linodes", []) or []),
                    }
                )
            return result

        data = self.client.get("/networking/vlans")
        return data.get("data", [])

    def config_view(self, linode_id: int, config_id: int) -> dict[str, Any]:
        return self.client.get(f"/linode/instances/{linode_id}/configs/{config_id}")

    def configs_list(self, linode_id: int) -> list[dict[str, Any]]:
        data = self.client.get(f"/linode/instances/{linode_id}/configs")
        return data.get("data", [])

    def config_update(self, linode_id: int, config_id: int, payload: dict[str, Any]) -> None:
        self.client.put(f"/linode/instances/{linode_id}/configs/{config_id}", data=payload)

    def shutdown(self, linode_id: int) -> None:
        self.client.post(f"/linode/instances/{linode_id}/shutdown")

    def boot(self, linode_id: int) -> None:
        self.client.post(f"/linode/instances/{linode_id}/boot")

    def reboot(self, linode_id: int) -> None:
        self.client.post(f"/linode/instances/{linode_id}/reboot")

    def status(self, linode_id: int) -> str:
        data = self.client.get(f"/linode/instances/{linode_id}")
        return str(data.get("status", ""))
