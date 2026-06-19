# pylinode-node-cache-manager

Node-level cache manager for Linode LKE. Manages prefetching and garbage collection of models and datasets on each node via DaemonSet.

## Features

- **Multi-source downloads**: Hugging Face, S3, HTTPS, OCI artifacts
- **Manifest-driven reconciliation**: Declare desired cache state; daemon maintains exact state
- **Garbage collection**: Automatic cleanup of stale/removed assets
- **Disk space aware**: Skips downloads if insufficient free disk
- **Checksum verification**: Optional SHA256 verification per asset
- **Prometheus metrics**: Built-in observability for download success/failure, cache size, disk usage
- **Non-root execution**: Runs as unprivileged user by default
- **Kubernetes-native**: Credentials via Kubernetes Secrets; env var configuration

## Installation

### Via Helm Chart

```bash
helm repo add linode-charts https://ram-pi.github.io/linode-charts
helm repo update
helm upgrade --install node-cache linode-charts/lke-node-cache-manager \
  --namespace node-cache \
  --create-namespace
```

### Local Development

```bash
git clone https://github.com/ram-pi/linode-charts.git
cd pylinode-node-cache-manager

# Install uv (pick one)
brew install uv
# or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Create .venv, install app + dev dependencies from pyproject/uv.lock
uv sync

# Run
uv run pylinode-node-cache-manager

# Test
uv run pytest
```

### Docker Build & Run Locally

```bash
cd pylinode-node-cache-manager

# Build the image
docker build -t pylinode-node-cache-manager:dev .

# Run with a local cache directory and an inline asset list
docker run --rm \
  -p 9191:8080 \
  -v /tmp/node-cache-local:/opt/node-cache \
  -e CACHE_PATH=/opt/node-cache \
  -e METRICS_PORT=8080 \
  -e RECONCILE_INTERVAL_SECONDS=300 \
  -e MIN_FREE_DISK_PERCENT=5 \
  -e ASSETS_JSON='[
    {
      "name": "robots",
      "source": "https",
      "ref": "https://huggingface.co/robots.txt",
      "version": "1",
      "destination": "test/robots.txt"
    }
  ]' \
  pylinode-node-cache-manager:dev
```

Pass credentials as additional `-e` flags:

```bash
docker run --rm \
  -p 9191:8080 \
  -v /tmp/node-cache-local:/opt/node-cache \
  -e CACHE_PATH=/opt/node-cache \
  -e METRICS_PORT=8080 \
  -e HF_TOKEN="<your-hf-token>" \
  -e AWS_ACCESS_KEY_ID="<your-access-key>" \
  -e AWS_SECRET_ACCESS_KEY="<your-secret-key>" \
  -e ASSETS_JSON='[
    {
      "name": "sd-v1-5",
      "source": "huggingface",
      "ref": "runwayml/stable-diffusion-v1-5",
      "version": "1.5.0",
      "destination": "models/sd-v1-5"
    }
  ]' \
  pylinode-node-cache-manager:dev
```

Check metrics from the host while the container is running:

```bash
curl http://127.0.0.1:9191/metrics | grep cache_
```

Inspect cached files written to the host mount:

```bash
ls -lh /tmp/node-cache-local/
```

> **Note**: The container runs as UID 1000. If `/tmp/node-cache-local` does not exist yet,
> create it first with the right ownership:
> ```bash
> mkdir -p /tmp/node-cache-local && sudo chown 1000 /tmp/node-cache-local
> ```

### Local Run Example (Custom Path + Models + Endpoints)

Use this example to run the daemon locally with:
- a specific cache path
- a list of model assets
- explicit source endpoints/references
- credentials for private sources

```bash
cd pylinode-node-cache-manager

# 1) Build a local manifest payload
ASSETS_JSON=$(cat <<'JSON'
[
  {
    "name": "sd-v1-5",
    "source": "huggingface",
    "ref": "runwayml/stable-diffusion-v1-5",
    "version": "1.5.0",
    "destination": "models/sd-v1-5",
    "credentials_ref": "hf-default"
  },
  {
    "name": "llama-3-8b",
    "source": "huggingface",
    "ref": "meta-llama/Meta-Llama-3-8B",
    "version": "8b-instruct",
    "destination": "models/llama-3-8b",
    "credentials_ref": "hf-default"
  },
  {
    "name": "clip-model-archive",
    "source": "https",
    "ref": "https://example-models.mycompany.com/clip/clip-model-v2.tar.gz",
    "version": "2026-06-01",
    "destination": "models/clip-v2",
    "credentials_ref": "https-default"
  },
  {
    "name": "vision-checkpoint",
    "source": "s3",
    "ref": "s3://my-ml-bucket/checkpoints/vision/vision-v3.bin",
    "version": "v3",
    "destination": "models/vision-v3",
    "credentials_ref": "s3-default"
  }
]
JSON
)

# 2) Set runtime configuration
export CACHE_PATH="/tmp/node-cache-local"
export ASSETS_JSON
export RECONCILE_INTERVAL_SECONDS="300"
export MIN_FREE_DISK_PERCENT="10"
export METRICS_PORT="8080"

# Optional auth for private endpoints
export HF_TOKEN="<your-hf-token>"
export AWS_ACCESS_KEY_ID="<your-access-key>"
export AWS_SECRET_ACCESS_KEY="<your-secret-key>"
# Optional token for private HTTPS model endpoints (if required by your endpoint)
export HTTPS_BEARER_TOKEN="<your-https-token>"

# Optional per-asset credentials (resolved from each asset.credentials_ref)
# Pattern: CREDENTIALS_<CREDENTIALS_REF_NORMALIZED>_<KEY>
# Example: "hf-default" -> "HF_DEFAULT"
export CREDENTIALS_HF_DEFAULT_HF_TOKEN="<hf-token-for-hf-default>"
export CREDENTIALS_S3_DEFAULT_AWS_ACCESS_KEY_ID="<s3-access-key-for-s3-default>"
export CREDENTIALS_S3_DEFAULT_AWS_SECRET_ACCESS_KEY="<s3-secret-for-s3-default>"
export CREDENTIALS_HTTPS_DEFAULT_HTTPS_BEARER_TOKEN="<https-token-for-https-default>"

# Precedence: per-asset CREDENTIALS_* values override global HF_TOKEN/AWS_*/HTTPS_BEARER_TOKEN
# for that specific asset download.

# 3) Run locally with uv
uv run pylinode-node-cache-manager
```

Check metrics while running:

```bash
curl http://127.0.0.1:8080/metrics | grep cache_
```

## Configuration

Configuration is env-driven. See [Helm chart values](../charts/lke-node-cache-manager/values.yaml) for full schema.

### Required Environment Variables

- `CACHE_PATH`: Absolute path to cache root (default: `/opt/node-cache`)
- `ASSETS_JSON`: JSON string or file path with array of cache entries (see schema below)

### Optional Environment Variables

- `METRICS_PORT`: Prometheus metrics listen port (default: `8080`)
- `RECONCILE_INTERVAL_SECONDS`: Reconcile loop interval (default: `900`)
- `MIN_FREE_DISK_PERCENT`: Minimum free disk % before skipping download (default: `10`)
- `DOWNLOAD_TIMEOUT_SECONDS`: Per-download timeout (default: `3600`)
- `LOG_LEVEL`: Logging level (default: `INFO`)
- `HF_TOKEN`: Hugging Face API token (optional)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: AWS credentials for S3 (optional)

### Asset Schema

Each cache entry in `ASSETS_JSON`:

```json
{
  "name": "stable-diffusion-1.5",
  "source": "huggingface",
  "ref": "runwayml/stable-diffusion-v1-5",
  "version": "1.5.0",
  "destination": "models/sd-1.5",
  "sha256": "optional-hash-for-verification",
  "credentials_ref": "optional-secret-name"
}
```

**Fields:**
- `name` (string, required): Unique identifier for this asset
- `source` (string, required): One of `huggingface`, `s3`, `https`, `oci`
- `ref` (string, required): Source-specific reference (model ID, S3 URI, URL, artifact ref)
- `version` (string, required): Version/hash for change detection
- `destination` (string, required): Path relative to cache root
- `sha256` (string, optional): Expected SHA256 hash; skipped if not provided
- `credentials_ref` (string, optional): Kubernetes Secret name for per-asset credentials

## Metrics

Prometheus metrics exposed on `http://<pod>:8080/metrics`:

- `cache_download_success_total{source,asset}`: Successful downloads
- `cache_download_failure_total{source,asset,reason}`: Failed downloads
- `cache_download_bytes_total{asset}`: Total bytes downloaded per asset
- `cache_gc_runs_total`: Total GC cycles
- `cache_gc_bytes_freed_total`: Bytes deleted by GC
- `cache_gc_failures_total`: GC cycle failures
- `node_disk_used_bytes`: Used disk space on node
- `node_disk_free_bytes`: Free disk space on node
- `cache_size_bytes`: Total cache directory size

Derived storage gauges are also exported in MB and GB for easier dashboards:

- `node_disk_used_megabytes`, `node_disk_free_megabytes`, `cache_size_megabytes`
- `node_disk_used_gigabytes`, `node_disk_free_gigabytes`, `cache_size_gigabytes`

Bytes remain the canonical unit for counters and gauges; the MB/GB metrics are derived views for humans and Grafana panels.

## Logs

Cache status logged periodically (INFO level):

```
Assets cached:
  stable-diffusion-1.5 (4.0 GB) at /opt/node-cache/models/sd-1.5
  training-data-2025 (50.0 GB) at /opt/node-cache/datasets/train-2025-01
Total: 54.0 GB | Free disk: 156.0 GB (75%)
```

## Development

### Project Structure

```
pylinode-node-cache-manager/
├── src/pylinode_node_cache_manager/
│   ├── __init__.py
│   ├── cli.py                 # Main entry, signal handling, logging
│   ├── config.py              # Env parsing, schema validation
│   ├── models.py              # Pydantic models, Source enum
│   ├── storage.py             # Filesystem operations
│   ├── downloader.py          # Download orchestration
│   ├── cache_manager.py       # Reconcile, GC logic
│   └── adapters/
│       ├── __init__.py
│       ├── base.py            # Abstract download adapter
│       ├── huggingface.py
│       ├── s3.py
│       ├── https.py
│       └── oci.py
├── tests/
│   ├── test_config.py
│   ├── test_storage.py
│   ├── test_downloader.py
│   ├── test_cache_manager.py
│   └── conftest.py
├── Dockerfile
├── pyproject.toml
├── main.py
└── README.md
```

### Testing

```bash
# Run all tests
uv run pytest

# With coverage
uv run pytest --cov=pylinode_node_cache_manager --cov-report=html

# Specific test
uv run pytest tests/test_cache_manager.py::test_gc_safety_boundary
```

### Linting

```bash
uv run black .
uv run ruff check .
```

### Dependency Management

```bash
# Add a runtime dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Refresh lockfile after dependency changes
uv lock
```

## Security Considerations

- **Non-root execution**: Runs as UID 1000 by default; fails if cache directory not writable
- **No privilege escalation**: No special capabilities required
- **Credential handling**: Secrets passed via Kubernetes Secret mounts; never logged
- **Download validation**: Checksum verification when provided; HTTPS-only for URLs
- **GC safety**: Hard boundary prevents deletion outside configured cache root
