from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from pylinode_vlan_topology_exporter.topology_ui_app import create_app


SAMPLE_METRICS = """
# HELP linode_vlan_scrape_success Last scrape success state
# TYPE linode_vlan_scrape_success gauge
linode_vlan_scrape_success 1
# HELP linode_vlan_attachment Linode attached to VLAN
# TYPE linode_vlan_attachment gauge
linode_vlan_attachment{vlan_label="vlan-a",region="us-ord",linode_id="1001",linode_label="node-a",config_id="0",interface_id="60",source="linode_interface",ipam_address="10.0.1.2/24"} 1
"""


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class TestTopologyUiApi(unittest.TestCase):
    @patch("pylinode_vlan_topology_exporter.topology_ui_app.httpx.get")
    def test_api_topology_returns_live_snapshot(self, get_mock) -> None:
        get_mock.return_value = FakeResponse(SAMPLE_METRICS)
        client = TestClient(create_app())

        response = client.get("/api/topology")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ui"]["status"], "ok")
        self.assertEqual(payload["summary"]["attachment_count"], 1)


if __name__ == "__main__":
    unittest.main()
