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
	@echo "   # Enable IP forwarding (persistent across reboots)"
	@echo "   sysctl -w net.ipv4.ip_forward=1"
	@echo "   echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf"
	@echo ""
	@echo "   # Allow forwarding between VLAN (eth1) and public (eth0)"
	@echo "   iptables -A FORWARD -i eth1 -o eth0 -j ACCEPT"
	@echo "   iptables -A FORWARD -i eth0 -o eth1 -m state --state RELATED,ESTABLISHED -j ACCEPT"
	@echo ""
	@echo "   # Masquerade outbound traffic so replies return to the correct node"
	@echo "   iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE"
	@echo ""
	@echo "   # (Optional) Persist iptables rules across reboots"
	@echo "   apt-get install -y iptables-persistent && netfilter-persistent save"
	@echo ""
	@echo "══════════════════════════════════════════════════════════════════════════"
	@echo ""

## delete-vlan-vm: Delete the VLAN test VM
.PHONY: delete-vlan-vm
delete-vlan-vm:
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

## lint: Lint all charts under charts/
.PHONY: lint
lint:
	helm lint charts/*

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^##' Makefile | sed 's/^## //'

.DEFAULT_GOAL := help
