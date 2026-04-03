# linode-charts Makefile

# ── LKE cluster defaults (override on the command line) ──────────────────────
CLUSTER_LABEL ?= linode-charts-test
REGION        ?= de-fra-2
K8S_VERSION   ?= 1.35
NODE_TYPE     ?= g6-standard-2
NODE_COUNT    ?= 3

# ── VLAN test VM defaults ─────────────────────────────────────────────────────
VM_LABEL      ?= vlan-test-vm
VM_TYPE       ?= g6-nanode-1
VM_IMAGE      ?= linode/ubuntu24.04
VLAN_LABEL    ?= private-lke
VLAN_IP       ?= 172.20.200.101/24

# ── LKE ──────────────────────────────────────────────────────────────────────

## create-lke: Create a test LKE cluster (requires linode-cli + LINODE_TOKEN)
.PHONY: create-lke
create-lke:
	linode-cli lke cluster-create \
		--label "$(CLUSTER_LABEL)" \
		--region "$(REGION)" \
		--k8s_version "$(K8S_VERSION)" \
		--node_pools '[{"type":"$(NODE_TYPE)","count":$(NODE_COUNT)}]'

## kubeconfig: Download kubeconfig for the cluster named CLUSTER_LABEL
.PHONY: kubeconfig
kubeconfig:
	$(eval CLUSTER_ID := $(shell linode-cli lke clusters-list --json | \
		jq -r '.[] | select(.label=="$(CLUSTER_LABEL)") | .id'))
	@test -n "$(CLUSTER_ID)" || (echo "Cluster '$(CLUSTER_LABEL)' not found"; exit 1)
	linode-cli lke kubeconfig-view $(CLUSTER_ID) --json \
		| jq -r '.[0].kubeconfig' \
		| base64 -d > kubeconfig-$(CLUSTER_LABEL).yaml
	@echo "Kubeconfig written to kubeconfig-$(CLUSTER_LABEL).yaml"
	@echo "Export with: export KUBECONFIG=\$$(pwd)/kubeconfig-$(CLUSTER_LABEL).yaml"

## delete-lke: Delete the test LKE cluster named CLUSTER_LABEL
.PHONY: delete-lke
delete-lke:
	$(eval CLUSTER_ID := $(shell linode-cli lke clusters-list --json | \
		jq -r '.[] | select(.label=="$(CLUSTER_LABEL)") | .id'))
	@test -n "$(CLUSTER_ID)" || (echo "Cluster '$(CLUSTER_LABEL)' not found"; exit 1)
	linode-cli lke cluster-delete $(CLUSTER_ID)
	@echo "Cluster $(CLUSTER_LABEL) (id=$(CLUSTER_ID)) deleted."

## add-node-pool: Add a node pool with a custom label to CLUSTER_LABEL
##   Override defaults: CLUSTER_LABEL, NODE_TYPE, POOL_COUNT, POOL_LABEL_KEY, POOL_LABEL_VALUE
##   Example: make add-node-pool CLUSTER_LABEL=my-cluster POOL_LABEL_KEY=node-type POOL_LABEL_VALUE=worker POOL_COUNT=2
POOL_COUNT       ?= 1
POOL_LABEL_KEY   ?= node-type
POOL_LABEL_VALUE ?= worker
.PHONY: add-node-pool
add-node-pool:
	$(eval CLUSTER_ID := $(shell linode-cli lke clusters-list --json | \
		jq -r '.[] | select(.label=="$(CLUSTER_LABEL)") | .id'))
	@test -n "$(CLUSTER_ID)" || (echo "Cluster '$(CLUSTER_LABEL)' not found"; exit 1)
	linode-cli lke pool-create $(CLUSTER_ID) \
		--type "$(NODE_TYPE)" \
		--count $(POOL_COUNT) \
		--labels '{"$(POOL_LABEL_KEY)":"$(POOL_LABEL_VALUE)"}'
	@echo "Node pool (type=$(NODE_TYPE) count=$(POOL_COUNT)) added to cluster $(CLUSTER_LABEL) with $(POOL_LABEL_KEY)=$(POOL_LABEL_VALUE)"

## add-excluded-pool: Add a node pool labelled lke-vlan-controller/exclude=true to CLUSTER_LABEL
##   Override defaults: CLUSTER_LABEL, NODE_TYPE, EXCLUDE_POOL_COUNT
##   Example: make add-excluded-pool CLUSTER_LABEL=my-cluster EXCLUDE_POOL_COUNT=2
EXCLUDE_POOL_COUNT ?= 1
.PHONY: add-excluded-pool
add-excluded-pool:
	$(eval CLUSTER_ID := $(shell linode-cli lke clusters-list --json | \
		jq -r '.[] | select(.label=="$(CLUSTER_LABEL)") | .id'))
	@test -n "$(CLUSTER_ID)" || (echo "Cluster '$(CLUSTER_LABEL)' not found"; exit 1)
	linode-cli lke pool-create $(CLUSTER_ID) \
		--type "$(NODE_TYPE)" \
		--count $(EXCLUDE_POOL_COUNT) \
		--labels '{"lke-vlan-exclude":"true"}'
	@echo "Node pool (type=$(NODE_TYPE) count=$(EXCLUDE_POOL_COUNT)) added to cluster $(CLUSTER_LABEL) with lke-vlan-exclude=true"

## list-lke: List all LKE clusters
.PHONY: list-lke
list-lke:
	@{ echo "ID\tLABEL\tREGION\tVERSION\tSTATUS"; \
	   linode-cli lke clusters-list --json | jq -r '.[] | [.id, .label, .region, .k8s_version, .status] | @tsv'; \
	} | column -t -s$$'\t'

# ── Helm ──────────────────────────────────────────────────────────────────────

## create-lke-enterprise: Create a test LKE Enterprise cluster (latest enterprise version auto-detected)
.PHONY: create-lke-enterprise
create-lke-enterprise:
	$(eval ENTERPRISE_VERSION := $(shell linode-cli lke tiered-versions-list enterprise --text 2>/dev/null | awk 'NR==2 {print $$1}'))
	@test -n "$(ENTERPRISE_VERSION)" || (echo "Could not detect latest LKE Enterprise version"; exit 1)
	@echo "Using LKE Enterprise version: $(ENTERPRISE_VERSION)"
	LINODE_CLI_API_VERSION=v4beta linode-cli lke cluster-create \
		--label "$(CLUSTER_LABEL)" \
		--region "$(REGION)" \
		--k8s_version "$(ENTERPRISE_VERSION)" \
		--tier enterprise \
		--node_pools '[{"type":"$(NODE_TYPE)","count":$(NODE_COUNT)}]'
	@echo ""
	@echo "ACTION REQUIRED: Control Plane ACLs are enabled by default on LKE Enterprise."
	@echo "   Add your IP to the cluster ACL in Linode Cloud Manager:"
	@echo "   https://cloud.linode.com/kubernetes/clusters"
	@echo "   (Cluster -> Control Plane ACL -> Add your IP)"
	@echo "   Without this step you will not be able to reach the API server."

# ── VLAN test VM ──────────────────────────────────────────────────────────────

## create-vlan-vm: Create a VM with a public IP and a VLAN interface for testing
##   Override defaults: VM_LABEL, VM_TYPE, VM_IMAGE, REGION, VLAN_LABEL, VLAN_IP
##   Example: make create-vlan-vm VLAN_LABEL=my-vlan VLAN_IP=10.0.0.254/24
.PHONY: create-vlan-vm
create-vlan-vm:
	@ROOT_PASS="$$(openssl rand -base64 24)"; \
	RESULT=$$(linode-cli linodes create \
		--label "$(VM_LABEL)" \
		--region "$(REGION)" \
		--type "$(VM_TYPE)" \
		--image "$(VM_IMAGE)" \
		--interfaces '[{"purpose":"public"},{"purpose":"vlan","label":"$(VLAN_LABEL)","ipam_address":"$(VLAN_IP)"}]' \
		--root_pass "$$ROOT_PASS" \
		--json); \
	echo "$$RESULT" | jq -r '.[0] | "Created: \(.label) (id=\(.id))  public_ip=\(.ipv4[0])"'; \
	PUBLIC_IP=$$(echo "$$RESULT" | jq -r '.[0].ipv4[0]'); \
	echo ""; \
	echo "SSH command: ssh root@$$PUBLIC_IP"; \
	echo "Password:    $$ROOT_PASS"; \
	echo ""; \
	echo "NOTE: VLAN interface will be active after the first boot."; \
	echo "      SSH in and verify with: ip addr show eth1"

## nat-gateway-setup: Print the commands to configure VM_LABEL as a NAT gateway
##   Run after create-vlan-vm. Requires the VM to be running (eth1 = VLAN interface).
##   Example: make nat-gateway-setup VM_LABEL=vlan-test-vm
.PHONY: nat-gateway-setup
nat-gateway-setup:
	$(eval VM_IP := $(shell linode-cli linodes list --json | \
		jq -r '.[] | select(.label=="$(VM_LABEL)") | .ipv4[0]'))
	@test -n "$(VM_IP)" || (echo "VM '$(VM_LABEL)' not found"; exit 1)
	@echo ""
	@echo "══ NAT gateway setup for $(VM_LABEL) ($(VM_IP)) ══════════════════════════"
	@echo ""
	@echo "1. SSH into the VM:"
	@echo "   ssh root@$(VM_IP)"
	@echo ""
	@echo "2. Run the following commands on the VM:"
	@echo ""
	@echo "   # Verify interface names (public=eth0, VLAN=eth1 on Linode virtio images)"
	@echo "   ip addr"
	@echo ""
	@echo "   # Enable IP forwarding (persistent via sysctl.d drop-in — Ubuntu 24.04 convention)"
	@echo "   echo 'net.ipv4.ip_forward = 1' | tee /etc/sysctl.d/99-ip-forward.conf"
	@echo "   sysctl --system"
	@echo ""
	@echo "   # Allow forwarding between VLAN (eth1) and public (eth0)"
	@echo "   iptables -A FORWARD -i eth1 -o eth0 -j ACCEPT"
	@echo "   iptables -A FORWARD -i eth0 -o eth1 -m state --state RELATED,ESTABLISHED -j ACCEPT"
	@echo ""
	@echo "   # Masquerade outbound traffic so replies return to the correct node"
	@echo "   iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE"
	@echo ""
	@echo "   # Persist iptables rules across reboots"
	@echo "   apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent && netfilter-persistent save"
	@echo ""
	@echo "══════════════════════════════════════════════════════════════════════════"
	@echo ""

## create-vpc-vm: Create a VM in the VPC subnet used by CLUSTER_LABEL (LKE Enterprise)
##   The VM uses a VPC-only interface with nat_1_1=any (same pattern as LKE Enterprise nodes).
##   Outputs the VPC IP (use as ZoneEgress address) and the 1:1 NAT public IP (SSH + egress).
##   Override defaults: VM_LABEL, VM_TYPE, VM_IMAGE, REGION, CLUSTER_LABEL
##   Example: make create-vpc-vm CLUSTER_LABEL=my-enterprise-cluster VM_LABEL=kuma-egress
.PHONY: create-vpc-vm
create-vpc-vm:
	$(eval CLUSTER_ID := $(shell LINODE_CLI_API_VERSION=v4beta linode-cli lke clusters-list --json | \
		jq -r '.[] | select(.label=="$(CLUSTER_LABEL)") | .id'))
	@test -n "$(CLUSTER_ID)" || (echo "Cluster '$(CLUSTER_LABEL)' not found"; exit 1)
	$(eval POOL_ID := $(shell LINODE_CLI_API_VERSION=v4beta linode-cli lke pools-list $(CLUSTER_ID) --json | \
		jq -r '.[0].id'))
	$(eval NODE_LINODE_ID := $(shell LINODE_CLI_API_VERSION=v4beta linode-cli lke pool-view $(CLUSTER_ID) $(POOL_ID) --json | \
		jq -r '[.[0].nodes[] | select(.status=="ready")][0].instance_id'))
	$(eval SUBNET_ID := $(shell linode-cli linodes configs-list $(NODE_LINODE_ID) --json | \
		jq -r '.[0].interfaces[] | select(.purpose=="vpc") | .subnet_id'))
	@test -n "$(SUBNET_ID)" || (echo "Could not find VPC subnet for cluster '$(CLUSTER_LABEL)'. Is it an LKE Enterprise cluster?"; exit 1)
	@echo "Resolved: cluster=$(CLUSTER_LABEL) node=$(NODE_LINODE_ID) subnet=$(SUBNET_ID)"
	@ROOT_PASS="$$(openssl rand -base64 24)"; \
	RESULT=$$(linode-cli linodes create \
		--label "$(VM_LABEL)" \
		--region "$(REGION)" \
		--type "$(VM_TYPE)" \
		--image "$(VM_IMAGE)" \
		--interfaces '[{"purpose":"vpc","subnet_id":$(SUBNET_ID),"ipv4":{"nat_1_1":"any"}}]' \
		--root_pass "$$ROOT_PASS" \
		--json); \
	LINODE_ID=$$(echo "$$RESULT" | jq -r '.[0].id'); \
	echo "$$RESULT" | jq -r '.[0] | "Created: \(.label) (id=\(.id))"'; \
	CONFIGS=$$(linode-cli linodes configs-list $$LINODE_ID --json 2>/dev/null); \
	VPC_IP=$$(echo "$$CONFIGS" | jq -r '.[0].interfaces[] | select(.purpose=="vpc") | .ipv4.address // empty'); \
	NAT_IP=$$(echo "$$CONFIGS" | jq -r '.[0].interfaces[] | select(.purpose=="vpc") | .ipv4.nat_1_1 // empty'); \
	echo ""; \
	echo "VPC IP  (ZoneEgress networking.address): $${VPC_IP:-"run: linode-cli linodes configs-list $$LINODE_ID --json"}"; \
	echo "NAT IP  (SSH + egress public IP):         $${NAT_IP:-"see Cloud Manager or linode-cli linodes configs-list $$LINODE_ID --json"}"; \
	echo "SSH:    ssh root@$${NAT_IP:-<NAT_IP>}"; \
	echo "Pass:   $$ROOT_PASS"

## delete-vlan-vm: Delete the VLAN test VM
.PHONY: delete-vlan-vm
delete-vlan-vm:
	$(eval VM_ID := $(shell linode-cli linodes list --json | \
		jq -r '.[] | select(.label=="$(VM_LABEL)") | .id'))
	@test -n "$(VM_ID)" || (echo "VM '$(VM_LABEL)' not found"; exit 1)
	linode-cli linodes delete $(VM_ID)
	@echo "VM $(VM_LABEL) (id=$(VM_ID)) deleted."

## delete-vpc-vm: Delete a VPC VM by label (e.g. make delete-vpc-vm VM_LABEL=kuma-egress)
.PHONY: delete-vpc-vm
delete-vpc-vm:
	$(eval VM_ID := $(shell linode-cli linodes list --json | \
		jq -r '.[] | select(.label=="$(VM_LABEL)") | .id'))
	@test -n "$(VM_ID)" || (echo "VM '$(VM_LABEL)' not found"; exit 1)
	linode-cli linodes delete $(VM_ID)
	@echo "VM $(VM_LABEL) (id=$(VM_ID)) deleted."

## list-vms: List all Linode VMs
.PHONY: list-vms
list-vms:
	@{ echo "ID\tLABEL\tREGION\tTYPE\tSTATUS\tIPv4"; \
	   linode-cli linodes list --json | jq -r '.[] | [.id, .label, .region, .type, .status, (.ipv4[0] // "-")] | @tsv'; \
	} | column -t -s$$'\t'

## Helm ──────────────────────────────────────────────────────────────────────

## verify-nat-gw: Spin up a debug pod and verify outbound IP matches NAT_GW_IP
##   Usage: make verify-nat-gw NAT_GW_IP=<public-ip> [NAMESPACE=default]
##   Example: make verify-nat-gw NAT_GW_IP=45.79.10.1 NAMESPACE=lke-route-injector
NAT_GW_IP ?=
NAMESPACE  ?= default
.PHONY: verify-nat-gw
verify-nat-gw:
	@test -n "$(NAT_GW_IP)" || (echo "NAT_GW_IP is required. Usage: make verify-nat-gw NAT_GW_IP=<ip>"; exit 1)
	./scripts/verify-nat-gw.sh "$(NAT_GW_IP)" "$(NAMESPACE)"

## lint: Lint all charts under charts/
.PHONY: lint
lint:
	helm lint charts/*

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^##' Makefile | sed 's/^## //'

.DEFAULT_GOAL := help
