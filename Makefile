# linode-charts Makefile

# ── LKE cluster defaults (override on the command line) ──────────────────────
CLUSTER_LABEL ?= linode-charts-test
REGION        ?= de-fra-2
K8S_VERSION   ?= 1.35
NODE_TYPE     ?= g6-standard-2
NODE_COUNT    ?= 3

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

## list-lke: List all LKE clusters
.PHONY: list-lke
list-lke:
	@{ echo "ID\tLABEL\tREGION\tVERSION\tSTATUS"; \
	   linode-cli lke clusters-list --json | jq -r '.[] | [.id, .label, .region, .k8s_version, .status] | @tsv'; \
	} | column -t -s$$'\t'

# ── Helm ──────────────────────────────────────────────────────────────────────

## lint: Lint all charts under charts/
.PHONY: lint
lint:
	helm lint charts/*

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^##' Makefile | sed 's/^## //'

.DEFAULT_GOAL := help
