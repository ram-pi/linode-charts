# linode-charts

A collection of Helm charts created and used within Linode / Akamai Cloud.

## Charts

| Chart | Version | Description |
|---|---|---|
| [lke-firewall-updater](charts/lke-firewall-updater/) | [![Version](https://img.shields.io/badge/dynamic/yaml?logo=helm&label=version&query=$.version&url=https://raw.githubusercontent.com/linode/linode-charts/main/charts/lke-firewall-updater/Chart.yaml)](https://github.com/linode/linode-charts/pkgs/container/lke-firewall-updater) | Syncs LKE node public IPs into a Linode Cloud Firewall rule — DaemonSet registers IPs on boot, CronJob removes stale ones |

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

## Demo LKE cluster

Use the Makefile to spin up a throwaway LKE cluster for testing chart installations.

**Prerequisites**: [`linode-cli`](https://github.com/linode/linode-cli) installed and `LINODE_TOKEN` exported.

```bash
# Create cluster with defaults (de-fra-2, k8s 1.35, 3× g6-standard-2)
make create-lke

# Override any default
make create-lke CLUSTER_LABEL=my-test REGION=us-east NODE_COUNT=2

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
