# linode-charts

A collection of Helm charts created and used within Linode / Akamai Cloud.

## Charts

| Chart | Version | Description |
|---|---|---|
| [lke-firewall-updater](charts/lke-firewall-updater/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-firewall-updater/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-firewall-updater) | Syncs LKE node public IPs into a Linode Cloud Firewall rule — DaemonSet registers IPs on boot, CronJob removes stale ones |
| [lke-vlan-controller](charts/lke-vlan-controller/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-vlan-controller/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-vlan-controller) | Attaches a VLAN interface to every node in a standard LKE cluster with rolling reboots and IPAM |
| [lke-vlan-controller-enterprise](charts/lke-vlan-controller-enterprise/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-vlan-controller-enterprise/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-vlan-controller-enterprise) | Variant of lke-vlan-controller for LKE Enterprise clusters (VPC-aware: shuts down nodes before config update, disables Linode Network Helper) |
| [lke-route-injector](charts/lke-route-injector/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-route-injector/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-route-injector) | Injects static IP routes on targeted LKE nodes via a DaemonSet — routes survive reboots and are re-applied on a configurable interval |

## Install from GHCR

Install the published chart directly from GitHub Container Registry:

```bash
helm upgrade --install lke-fw-updater oci://ghcr.io/ram-pi/lke-firewall-updater \
	--version 0.1.0 \
	--namespace lke-firewall-updater \
	--create-namespace \
	--set-json 'firewall.ids=[12345]' \
	--set linodeToken=<YOUR_LINODE_TOKEN>
```

For chart-specific values and more installation options, see [charts/lke-firewall-updater/README.md](charts/lke-firewall-updater/README.md).

## Related projects

### Core controllers

| Repository | Description |
|---|---|
| [linode-cloud-controller-manager](https://github.com/linode/linode-cloud-controller-manager) | Kubernetes Cloud Controller Manager — NodeBalancer integration and node lifecycle |
| [cloud-firewall-controller](https://github.com/linode/cloud-firewall-controller) | Manages Linode Cloud Firewalls as Kubernetes network policies |
| [linode-blockstorage-csi-driver](https://github.com/linode/linode-blockstorage-csi-driver) | CSI driver for Linode Block Storage persistent volumes |
| [linode-cosi-driver](https://github.com/linode/linode-cosi-driver) | COSI driver for Linode Object Storage |

### Cluster provisioning

| Repository | Description |
|---|---|
| [cluster-api-provider-linode](https://github.com/linode/cluster-api-provider-linode) | Cluster API (CAPL) — declarative LKE cluster lifecycle |
| [karpenter-provider-linode](https://github.com/linode/karpenter-provider-linode) | Karpenter provider for automated node scaling |
| [provider-linode](https://github.com/linode/provider-linode) | Crossplane provider for Linode infrastructure |

### DNS, TLS & observability

| Repository | Description |
|---|---|
| [cert-manager-webhook-linode](https://github.com/linode/cert-manager-webhook-linode) | cert-manager ACME DNS-01 webhook for Linode DNS Manager |

### Backup & storage

| Repository | Description |
|---|---|
| [velero-plugin](https://github.com/linode/velero-plugin) | Velero plugin — clones Linode CSI volumes for backup |
| [provider-ceph](https://github.com/linode/provider-ceph) | Crossplane provider for Ceph / S3-compatible object storage |

### Platform

| Repository | Description |
|---|---|
| [apl-core](https://github.com/linode/apl-core) | App Platform for LKE — GitOps-based deployment with Argo CD |
| [apl-charts](https://github.com/linode/apl-charts) | App Platform catalog Helm charts |

## Install from GHCR

All charts are published to GitHub Container Registry on every push to `main` (or on version tag). Install any chart directly:

```bash
# lke-vlan-controller
helm upgrade --install lke-vlan-controller oci://ghcr.io/ram-pi/lke-vlan-controller \
  --version 0.1.0 --namespace lke-vlan-controller --create-namespace \
  --set vlan.name=my-vlan --set vlan.cidr=172.20.200.0/24 --set linodeToken=<TOKEN>

# lke-route-injector
helm upgrade --install lke-route-injector oci://ghcr.io/ram-pi/lke-route-injector \
  --version 0.1.0 --namespace lke-route-injector --create-namespace \
  --set 'routes[0].network=0.0.0.0/0' --set 'routes[0].gateway=172.20.200.1' \
  --set deployment.vlanNodesOnly=true
```

For chart-specific values and options see each chart's `README.md`.

## Demo LKE cluster

Use the Makefile to spin up a throwaway LKE cluster for testing chart installations.

**Prerequisites**: [`linode-cli`](https://github.com/linode/linode-cli) installed and `LINODE_TOKEN` exported.

```bash
# Create cluster with defaults (de-fra-2, k8s 1.35, 3× g6-standard-2)
make create-lke

# Override any default
make create-lke CLUSTER_LABEL=my-test REGION=us-east NODE_COUNT=2

# Create an LKE Enterprise cluster (latest enterprise version auto-detected)
make create-lke-enterprise

# Download kubeconfig once the cluster is ready
make kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig-linode-charts-test.yaml

# List all your LKE clusters
make list-lke

# Tear it down when done
make delete-lke
```

Default values (can all be overridden on the command line):

| Variable | Default |
|---|---|
| `CLUSTER_LABEL` | `linode-charts-test` |
| `REGION` | `de-fra-2` |
| `K8S_VERSION` | `1.35` |
| `NODE_TYPE` | `g6-standard-2` |
| `NODE_COUNT` | `3` |

## VLAN test VM

Spin up a Linode VM pre-attached to a VLAN for testing NAT gateway and route injection scenarios:

```bash
# Create a VM with public + VLAN interfaces
make create-vlan-vm VLAN_LABEL=private-lke VLAN_IP=172.20.200.101/24

# Print commands to configure it as a NAT gateway
make nat-gateway-setup VM_LABEL=vlan-test-vm

# Add a node pool labelled lke-vlan-exclude=true (skipped by lke-vlan-controller)
make add-excluded-pool CLUSTER_LABEL=linode-charts-test

# Delete the VM when done
make delete-vlan-vm
```

See [USE_CASES.md](USE_CASES.md) for a full end-to-end NAT gateway walkthrough.
