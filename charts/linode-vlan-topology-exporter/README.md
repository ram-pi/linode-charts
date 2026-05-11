# linode-vlan-topology-exporter

Deploys `pylinode-vlan-topology-exporter` on Kubernetes and exposes Prometheus metrics via a configurable Service type.

## Install

```bash
helm upgrade --install linode-vlan-topology-exporter ./charts/linode-vlan-topology-exporter \
  --namespace linode-vlan-topology-exporter \
  --create-namespace \
  --set existingSecret=linode-token
```

## Service exposure

Set `service.type` based on your environment:

- `ClusterIP` (default)
- `NodePort`
- `LoadBalancer`

Example:

```bash
helm upgrade --install linode-vlan-topology-exporter ./charts/linode-vlan-topology-exporter \
  --namespace linode-vlan-topology-exporter \
  --create-namespace \
  --set existingSecret=linode-token \
  --set service.type=LoadBalancer
```

## Required values

- Provide token via one of:
  - `existingSecret` (recommended)
  - `linodeToken`

## Key values

- `image.repository` / `image.tag`: exporter image (defaults to GHCR image)
- `exporter.scrapeIntervalSeconds`: collection interval
- `exporter.maxWorkers`: concurrent Linode jobs
- `exporter.maxRps`: API rate cap
- `exporter.vlanLabelFilter`: optional prefix filter
- `service.type`: service exposure type
- `service.port`: service port (default `9108`)
