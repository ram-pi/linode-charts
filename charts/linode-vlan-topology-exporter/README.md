# linode-vlan-topology-exporter

Deploys `pylinode-vlan-topology-exporter` on Kubernetes and exposes Prometheus metrics via a configurable Service type.

Optionally, the chart can run the live read-only topology UI as a separate Deployment (second pod). The UI reads only the exporter Service `/metrics` endpoint.

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

When UI is enabled, a second Service is created for the UI endpoint:

- `<release>-linode-vlan-topology-exporter-ui`

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
- `ui.enabled`: enable topology UI Deployment (default `false`)
- `ui.image.repository` / `ui.image.tag`: UI image
- `ui.port`: UI container port (default `9200`)
- `ui.refreshSeconds`: frontend auto-refresh interval (default `60`)
- `ui.service.enabled`: create UI Service (default `true` when UI enabled)
- `ui.service.type`: UI Service type
- `ui.service.port`: UI Service port (default `9200`)

## Enable UI

```bash
helm upgrade --install linode-vlan-topology-exporter ./charts/linode-vlan-topology-exporter \
  --namespace linode-vlan-topology-exporter \
  --create-namespace \
  --set existingSecret=linode-token \
  --set ui.enabled=true
```
