# LKE Node Cache Manager Helm Chart

Deploy a DaemonSet to prefetch and manage cached assets (models, datasets, files) on every node in a Linode Kubernetes Engine (LKE) cluster.

## Features

- **Multi-source support**: Hugging Face, S3, HTTPS URLs, OCI artifacts
- **Manifest-driven reconciliation**: Declare desired cache state; daemon maintains exact state
- **Garbage collection**: Automatic cleanup of stale/removed assets
- **Disk-space aware**: Skips downloads if insufficient free disk
- **Checksum verification**: Optional SHA256 verification per asset
- **Prometheus metrics**: Built-in observability for download success/failure, cache size, disk usage
- **Non-root execution**: Runs as unprivileged user (UID 1000) by default
- **Kubernetes-native**: Credentials via Kubernetes Secrets; env var configuration

## Prerequisites

- Linode Kubernetes Engine (LKE) cluster, v1.31+
- Helm 3.x
- kubectl configured to access your cluster

## Installation

### Quick Start

```bash
# From the repository root, install from GHCR using the example CPU LocalAI cache values
helm upgrade --install node-cache oci://ghcr.io/ram-pi/lke-node-cache-manager \
  --version 0.1.0 \
  --namespace node-cache \
  --create-namespace \
  --values examples/lke-node-cache-manager.values.yaml
```

From a local checkout, use `./charts/lke-node-cache-manager` instead of the OCI URL.

### With Custom Assets

Create a values file `my-cache-values.yaml`:

```yaml
assets:
  - name: "stable-diffusion-1.5"
    source: "huggingface"
    ref: "runwayml/stable-diffusion-v1-5"
    version: "1.5.0"
    destination: "models/sd-1.5"
    sha256: "optional-expected-hash"
    # credentials_ref: "huggingface-secret"  # Optional per-asset secret

  - name: "training-data"
    source: "s3"
    ref: "s3://my-bucket/datasets/train-2025.tar.gz"
    version: "2025-01-15"
    destination: "datasets/train-2025"

  - name: "additional-files"
    source: "https"
    ref: "https://example.com/files/data.zip"
    version: "1.0.0"
    destination: "files/data"

cacheRoot: /mnt/node-cache  # Custom cache location

reconcileIntervalSeconds: 600  # Check every 10 minutes

minFreeDiskPercent: 15  # Skip downloads if less than 15% free
```

Install with custom assets:

```bash
helm upgrade --install node-cache oci://ghcr.io/ram-pi/lke-node-cache-manager \
  --version 0.1.0 \
  --namespace node-cache \
  --create-namespace \
  --values my-cache-values.yaml
```

### With Authentication (HuggingFace Token)

If downloading private Hugging Face models, pass the token as a Kubernetes Secret:

```bash
# Create secret
kubectl create secret generic hf-credentials \
  --from-literal=token=hf_xxxxxxxxxxxx \
  -n node-cache

# Update values
echo "credentials:
  huggingface_token: $(kubectl get secret hf-credentials -n node-cache -o jsonpath='{.data.token}' | base64 -d)" >> my-cache-values.yaml

helm upgrade --install node-cache oci://ghcr.io/ram-pi/lke-node-cache-manager \
  --version 0.1.0 \
  --namespace node-cache \
  --values my-cache-values.yaml
```

### With S3 Credentials

For S3 downloads, pass AWS credentials:

```yaml
credentials:
  aws_access_key_id: "AKIA..."
  aws_secret_access_key: "..."
```

Or use environment-specific values files and Secret injection for production.

## Updating Cache Assets

To add, update, or remove assets:

1. Edit your values file
2. Run helm upgrade:

```bash
helm upgrade node-cache oci://ghcr.io/ram-pi/lke-node-cache-manager \
  --version 0.1.0 \
  --namespace node-cache \
  --create-namespace \
  --values my-cache-values.yaml
```

The DaemonSet will automatically roll (due to checksum annotation), and the new reconciliation will:
- Download any new assets
- Update any assets with changed versions
- Delete any assets removed from the list (garbage collection)

## Integrating Cached Assets in Workloads

Once assets are cached on nodes, workloads can access them via hostPath or emptyDir + volumeMount from node cache. **No PVC or storage provisioner needed.**

### Example 1: Pod with hostPath

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ai-app
spec:
  containers:
    - name: app
      image: my-ai-app:latest
      volumeMounts:
        - name: cache
          mountPath: /models
          readOnly: true
  volumes:
    - name: cache
      hostPath:
        path: /opt/node-cache/models
        type: Directory
```

### Example 2: Deployment with node affinity

Ensure replicas run on nodes with cache available:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-app
  template:
    metadata:
      labels:
        app: ai-app
    spec:
      affinity:
        # Prefer nodes that are already cached
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              preference:
                matchExpressions:
                  - key: "kubernetes.io/hostname"
                    operator: In
                    values: []  # Populate with cached node names via automation
      containers:
        - name: app
          image: my-ai-app:latest
          volumeMounts:
            - name: models-cache
              mountPath: /models
              readOnly: true
      volumes:
        - name: models-cache
          hostPath:
            path: /opt/node-cache/models
            type: Directory
```

## Monitoring & Metrics

Metrics are exposed on `http://<pod-ip>:8080/metrics` in Prometheus format.

### Key Metrics

- `cache_download_success_total{source,asset}` — Successful downloads by source and asset name
- `cache_download_failure_total{source,asset,reason}` — Failed downloads with failure reason
- `cache_download_bytes_total{asset}` — Total bytes downloaded per asset
- `cache_asset_declared{asset,source,ref,version,destination}` — Declared assets from manifest (`1` when configured)
- `cache_asset_present{asset,destination}` — Whether asset destination currently exists on disk (`1` or `0`)
- `cache_asset_size_bytes{asset,destination}` — Current on-disk size for each configured asset destination
- `cache_gc_runs_total` — Total garbage collection cycles
- `cache_gc_bytes_freed_total` — Total bytes freed by GC
- `cache_gc_failures_total` — GC cycle failures
- `node_disk_used_bytes` — Used disk space on node
- `node_disk_free_bytes` — Free disk space on node
- `cache_size_bytes` — Total cache directory size

### Scraping Configuration

Create a ServiceMonitor (if using Prometheus Operator):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: node-cache-metrics
  namespace: node-cache
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: lke-node-cache-manager
  endpoints:
    - port: metrics
      interval: 30s
```

Or use Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: 'node-cache'
    kubernetes_sd_configs:
      - role: service
        namespaces:
          names:
            - node-cache
    relabel_configs:
      - source_labels: [__meta_kubernetes_service_label_app_kubernetes_io_name]
        regex: lke-node-cache-manager
        action: keep
```

## Logs

View logs from a cache manager pod:

```bash
# List pods
kubectl get pods -n node-cache

# View logs
kubectl logs -n node-cache <pod-name>

# Follow logs in real-time
kubectl logs -n node-cache <pod-name> -f
```

Cache status is logged periodically at INFO level:

```
Assets cached:
  stable-diffusion-1.5 (4.0 GB) at /opt/node-cache/models/sd-1.5
  training-data (50.0 GB) at /opt/node-cache/datasets/train-2025
Total: 54.0 GB | Free disk: 156.0 GB (75%)
```

## Security

- **Non-root execution**: Container runs as UID 1000 (non-root) by default
- **No privilege escalation**: `allowPrivilegeEscalation: false`
- **Minimal capabilities**: Dropped `ALL` capabilities; cache manager needs no special privileges
- **Read-only cache mounts**: Workload pods mount cache with `readOnly: true`
- **Credential isolation**: Secrets passed via Kubernetes Secret objects (not in values YAML)
- **No host network**: DaemonSet runs in pod network namespace (not privileged)

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl describe pod -n node-cache <pod-name>

# Check logs for startup errors
kubectl logs -n node-cache <pod-name>
```

Common issues:
- **Permission denied on cache path**: By default, the chart runs an `init-cache-permissions` initContainer that sets ownership and mode on `cacheRoot`. If this still occurs, check initContainer logs and node-level hostPath permissions.
- **Insufficient disk space**: Free up space or adjust `minFreeDiskPercent` in values
- **Invalid asset configuration**: Check syntax of assets list; all required fields must be present

### Assets Not Downloading

```bash
# Check metrics for failure reasons
kubectl port-forward -n node-cache <pod-name> 8080:8080
curl http://localhost:8080/metrics | grep cache_download_failure
```

- **Network issues**: Ensure cluster nodes have internet access (or can reach asset sources via proxy)
- **Invalid credentials**: Verify tokens/keys are valid
- **Source unavailable**: Confirm source URL/reference is correct

### Disk Space Issues

```bash
# Check cache size and available disk
kubectl exec -n node-cache <pod-name> -- df -h /opt/node-cache
```

- Increase `minFreeDiskPercent` threshold if you want stricter checks
- Monitor `cache_size_bytes` and `node_disk_free_bytes` metrics for capacity planning
- Manually delete stale cache entries if needed: `kubectl exec -n node-cache <pod-name> -- rm -rf /opt/node-cache/path/to/asset`

## Chart Configuration Reference

See `values.yaml` for all configurable options, including:

- `cacheRoot` — Host path for cache storage
- `assets` — List of cache entries (required)
- `reconcileIntervalSeconds` — How often to check for updates
- `minFreeDiskPercent` — Minimum free disk % before skipping downloads
- `downloadTimeoutSeconds` — Timeout for individual downloads
- `credentials.*` — Global authentication tokens
- `deployment.image.*` — Docker image and tag
- `deployment.resources.*` — CPU/memory requests and limits
- `deployment.nodeSelector`, `tolerations` — Node targeting

## General Purpose Use Cases

This chart is not limited to AI models. You can cache any data:

- **Machine learning models**: Hugging Face, PyTorch Hub, ONNX models
- **Training datasets**: Large CSV files, TFRecord archives, parquet datasets
- **Static files**: Binaries, configuration files, reference data
- **Container base layers**: Pre-downloaded OCI artifacts
- **Documentation**: Offline docs, reference materials
- **Application data**: Frequently accessed static content

Define your cache entries in the assets list and the daemon will manage them just like models.
