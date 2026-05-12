from __future__ import annotations

import unittest

from pylinode_vlan_topology_exporter.topology_ui_model import parse_topology_metrics


SAMPLE_METRICS = """
# HELP linode_vlan_scrape_success Last scrape success state
# TYPE linode_vlan_scrape_success gauge
linode_vlan_scrape_success 1
# HELP linode_vlan_scrape_duration_seconds Last scrape duration in seconds
# TYPE linode_vlan_scrape_duration_seconds gauge
linode_vlan_scrape_duration_seconds 2.013
# HELP linode_vlan_api_rate_limit_hits_total Number of Linode API requests that hit rate limiting
# TYPE linode_vlan_api_rate_limit_hits_total counter
linode_vlan_api_rate_limit_hits_total 3
# HELP linode_vlan_info VLAN metadata record
# TYPE linode_vlan_info gauge
linode_vlan_info{vlan_label="vlan-a",region="us-ord"} 1
# HELP linode_vlan_linode_count Number of attached Linodes reported by VLAN list
# TYPE linode_vlan_linode_count gauge
linode_vlan_linode_count{vlan_label="vlan-a",region="us-ord"} 2
# HELP linode_vlan_attachment Linode attached to VLAN
# TYPE linode_vlan_attachment gauge
linode_vlan_attachment{vlan_label="vlan-a",region="us-ord",linode_id="1001",linode_label="node-a",config_id="13",interface_id="0",source="config",ipam_address="10.0.1.2/24"} 1
linode_vlan_attachment{vlan_label="vlan-a",region="us-ord",linode_id="1001",linode_label="node-a",config_id="0",interface_id="60",source="linode_interface",ipam_address="10.0.1.2/24"} 1
linode_vlan_attachment{vlan_label="vlan-a",region="us-ord",linode_id="1002",linode_label="node-b",config_id="19",interface_id="0",source="config",ipam_address="10.0.1.3/24"} 1
"""


class TestTopologyUiModel(unittest.TestCase):
    def test_parse_metrics_snapshot(self) -> None:
        snapshot = parse_topology_metrics(SAMPLE_METRICS)

        self.assertEqual(snapshot["scrape"]["success"], 1)
        self.assertEqual(snapshot["summary"]["vlan_count"], 1)
        self.assertEqual(snapshot["summary"]["attachment_count"], 2)
        self.assertEqual(snapshot["summary"]["unique_linode_count"], 2)
        self.assertEqual(len(snapshot["vlans"]), 1)
        self.assertEqual(snapshot["vlans"][0]["attached_linode_count"], 2)

        sources = {item["source"] for item in snapshot["attachments"]}
        self.assertIn("linode_interface", sources)


if __name__ == "__main__":
    unittest.main()
