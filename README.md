# linode-charts

A collection of Helm charts created and used within Linode / Akamai Cloud.

## Charts

| Chart | Version | Description |
|---|---|---|
| [lke-firewall-updater](charts/lke-firewall-updater/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-firewall-updater/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-firewall-updater) | Keeps cloud firewall rules in sync with Kubernetes node public IPs — supports Linode Cloud Firewalls, AWS Security Groups, and GCP VPC Firewall Rules simultaneously; event-driven single-writer controller with leader election eliminates concurrent-write race conditions |
| [lke-vlan-controller](charts/lke-vlan-controller/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-vlan-controller/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-vlan-controller) | Attaches a VLAN interface to every node in a standard LKE cluster with rolling reboots and IPAM |
| [lke-vlan-controller-enterprise](charts/lke-vlan-controller-enterprise/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-vlan-controller-enterprise/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-vlan-controller-enterprise) | Variant of lke-vlan-controller for LKE Enterprise clusters (VPC/NAT 1:1). Preserves the Linode Network Helper and ensures IPv6 SLAAC and routable IPv6 when attaching VLAN interfaces. |
| [lke-route-injector](charts/lke-route-injector/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/ram-pi/linode-charts/main/charts/lke-route-injector/Chart.yaml)](https://github.com/ram-pi/linode-charts/pkgs/container/lke-route-injector) | Injects static IP routes on targeted LKE nodes via a DaemonSet — routes survive reboots and are re-applied on a configurable interval |

## Install from GHCR

All charts are published to GitHub Container Registry. You can install them directly via OCI:

### lke-firewall-updater
```bash
helm upgrade --install lke-fw-updater oci://ghcr.io/ram-pi/lke-firewall-updater \
	--version 0.2.1 \
	--namespace lke-firewall-updater \
	--create-namespace \
	--set-json 'providers.linode.firewall.ids=[12345]' \
	--set providers.linode.token=<YOUR_LINODE_TOKEN>
```

### lke-vlan-controller
```bash
helm upgrade --install lke-vlan-controller oci://ghcr.io/ram-pi/lke-vlan-controller \
  --version 0.2.0 --namespace lke-vlan-controller --create-namespace \
  --set vlan.name=my-vlan --set vlan.cidr=172.20.200.0/24 --set linodeToken=<TOKEN>
```

### lke-vlan-controller-enterprise
```bash
helm upgrade --install lke-vlan-controller-enterprise oci://ghcr.io/ram-pi/lke-vlan-controller-enterprise \
  --version 0.2.2 --namespace lke-vlan-controller --create-namespace \
  --set vlan.name=my-vlan --set vlan.cidr=172.20.200.0/24 --set linodeToken=<TOKEN>
```

### lke-route-injector
```bash
helm upgrade --install lke-route-injector oci://ghcr.io/ram-pi/lke-route-injector \
  --version 0.2.0 --namespace lke-route-injector --create-namespace \
  --set 'routes[0].network=0.0.0.0/0' --set 'routes[0].gateway=172.20.200.1' \
  --set 'deployment.nodeSelector.lke-vlan-controller-status=completed'
```

For chart-specific values and more installation options, see each chart's `README.md`.

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

## Test Infrastructure

Use the provided Makefile to spin up throwaway infrastructure for testing.

**Prerequisites**: [`linode-cli`](https://github.com/linode/linode-cli) installed and `LINODE_TOKEN` exported.

### LKE Clusters

```bash
# Create cluster with defaults (de-fra-2, k8s 1.35, 3× g6-standard-2)
make create-lke

# Override defaults
make create-lke CLUSTER_LABEL=my-test REGION=us-east NODE_COUNT=2

# Add a node pool with a custom label (e.g. for lke-firewall-updater)
make add-node-pool CLUSTER_LABEL=linode-charts-test POOL_LABEL_KEY=node-type POOL_LABEL_VALUE=worker

# Download kubeconfig
make kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig-linode-charts-test.yaml

# Tear it down when done
make delete-lke
```

Default variables: `CLUSTER_LABEL` (linode-charts-test), `REGION` (de-fra-2), `K8S_VERSION` (1.35), `NODE_TYPE` (g6-standard-2), `NODE_COUNT` (3).

### Test VMs

#### Standard VLAN VM
Spin up a VM pre-attached to a VLAN for testing NAT gateway and route injection:

```bash
# Create a VM with public + VLAN interfaces
make create-vlan-vm VLAN_LABEL=private-lke VLAN_IP=172.20.200.101/24

# Print commands to configure it as a NAT gateway
make nat-gateway-setup VM_LABEL=vlan-test-vm

# Delete the VM when done
make delete-vlan-vm
```

See [USE_CASES.md](USE_CASES.md) for a full end-to-end NAT gateway walkthrough.
