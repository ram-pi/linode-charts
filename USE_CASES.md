# Use Cases

Practical end-to-end scenarios that combine the charts and Makefile targets in this repository.

---

## Use Case 1 — LKE NAT Gateway via VLAN

Route all outbound traffic from an LKE cluster through a dedicated Linode VM acting as a NAT gateway. Cluster nodes reach the internet through the VM's public IP, which is useful when you need a **single, predictable egress IP** for allowlisting in firewalls, third-party APIs, or compliance requirements.

![NAT Gateway Architecture](docs/architecture/nat_gateway.excalidraw.svg)

### Step 1 — Create the LKE cluster

```bash
make create-lke CLUSTER_LABEL=my-cluster REGION=de-fra-2 NODE_COUNT=3
make kubeconfig CLUSTER_LABEL=my-cluster
export KUBECONFIG=$(pwd)/kubeconfig-my-cluster.yaml
```

### Step 2 — Create the NAT gateway VM

The VM is created with a public interface (`eth0`) and a VLAN interface (`eth1`) pre-attached. Assign it the gateway IP of your chosen VLAN subnet.

```bash
make create-vlan-vm \
  VM_LABEL=nat-gateway \
  VLAN_LABEL=private-lke \
  VLAN_IP=172.20.200.1/24
```

### Step 3 — Configure the VM as a NAT gateway

```bash
make nat-gateway-setup VM_LABEL=nat-gateway
```

SSH into the VM and run the printed commands. They enable IP forwarding and install the `iptables` MASQUERADE rule so traffic arriving on `eth1` (VLAN) is forwarded out `eth0` (public) with the VM's public IP.

### Step 4 — Attach the VLAN interface to every LKE node

Deploy `lke-vlan-controller`. It will automatically detect each LKE node, assign it a free IP from the VLAN subnet, update the Linode config, and perform a rolling reboot to activate the interface.

```bash
helm upgrade --install lke-vlan-controller charts/lke-vlan-controller \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=private-lke \
  --set vlan.cidr=172.20.200.0/24 \
  --set linodeToken=$LINODE_TOKEN \
  --set-json 'vlan.excludedIPs=["172.20.200.1"]'
```

The `excludedIPs` entry reserves the gateway VM's VLAN IP so the controller never assigns it to a cluster node.

Wait until all nodes have the `vlan-ip` label:

```bash
kubectl get nodes -L vlan-ip,lke-vlan-controller-status
```

### Step 5 — Inject the default route on every LKE node

Deploy `lke-route-injector` to replace the default route on each node, steering all outbound traffic through the NAT gateway VM. Scope it to VLAN-enabled nodes only via `nodeSelector`.

```bash
helm upgrade --install lke-route-injector charts/lke-route-injector \
  --namespace lke-route-injector \
  --create-namespace \
  --set 'routes[0].network=0.0.0.0/0' \
  --set 'routes[0].gateway=172.20.200.1' \
  --set 'deployment.nodeSelector.lke-vlan-controller-status=completed'
```

The `nodeSelector` ensures the route injector only runs on nodes where `lke-vlan-controller` has completed the VLAN setup and reboot.

> **Note:** The Kubernetes API server must remain reachable after the default route changes. LKE control plane traffic uses the cluster's internal network, which is unaffected. If you use a Control Plane ACL (LKE Enterprise), ensure the NAT gateway VM's public IP is in the allowlist.

### Step 6 — Verify egress IP

Run a one-shot debug pod that queries `ifconfig.me` and verifies the returned IP matches the NAT gateway VM's public IP.

```bash
make verify-nat-gw NAT_GW_IP=<nat-gateway-public-ip>
```

Expected output: `PASS: outbound traffic is exiting via the NAT gateway (<ip>)`.

### Teardown

```bash
helm uninstall lke-route-injector -n lke-route-injector
helm uninstall lke-vlan-controller -n lke-vlan-controller
make delete-vlan-vm VM_LABEL=nat-gateway
make delete-lke CLUSTER_LABEL=my-cluster
```

---

## Use Case 2 — Node-Level ML Model Caching

Pre-download and cache large AI/ML models and datasets on every LKE node to eliminate cold-start latency for ML workloads. Once cached, pods can mount the node-local cache via hostPath, enabling instant model access without network I/O or storage provisioning.

### Scenario

You have a team running inference workloads on LKE that require large models (e.g., Stable Diffusion 4GB, LLaMA 7B+). Every new pod currently waits for the model to download from Hugging Face or S3, causing 5–10 minute startup delays. You want to pre-cache these models on all nodes so pods start in seconds.

### Step 1 — Create the LKE cluster

```bash
make create-lke CLUSTER_LABEL=ml-cluster REGION=de-fra-2 NODE_COUNT=3
make kubeconfig CLUSTER_LABEL=ml-cluster
export KUBECONFIG=$(pwd)/kubeconfig-ml-cluster.yaml
```

### Step 2 — Deploy the node cache manager

Create a values file `ml-cache-values.yaml`:

```yaml
cacheRoot: /mnt/ml-cache

assets:
  - name: "stable-diffusion-1.5"
    source: "huggingface"
    ref: "runwayml/stable-diffusion-v1-5"
    version: "1.5.0"
    destination: "models/sd-1.5"
    # sha256: "optional-expected-hash"

  - name: "llama-2-7b"
    source: "huggingface"
    ref: "meta-llama/Llama-2-7b"
    version: "2024-01-01"
    destination: "models/llama-2-7b"

  - name: "training-dataset-2025"
    source: "s3"
    ref: "s3://my-ml-bucket/datasets/train-2025-01.tar.gz"
    version: "2025-01-15"
    destination: "datasets/train-2025-01"

reconcileIntervalSeconds: 600  # Check every 10 minutes
minFreeDiskPercent: 10          # Don't download if <10% free disk
```

Deploy the chart:

```bash
helm upgrade --install ml-cache oci://ghcr.io/ram-pi/lke-node-cache-manager \
  --version 0.1.0 \
  --namespace node-cache \
  --create-namespace \
  --values ml-cache-values.yaml
```

### Step 3 — Verify cache is populated

```bash
# Check pod logs
kubectl logs -n node-cache -l app.kubernetes.io/name=lke-node-cache-manager | grep -i "assets cached"

# Check metrics
POD=$(kubectl get pod -n node-cache -l app.kubernetes.io/name=lke-node-cache-manager -o jsonpath='{.items[0].metadata.name}')
kubectl port-forward -n node-cache $POD 8080:8080 &
curl http://localhost:8080/metrics | grep cache_size_bytes
```

### Step 4 — Deploy ML workload that uses the cache

Create an inference pod that mounts the cached models:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: inference-worker
spec:
  containers:
    - name: inference
      image: ml-inference-app:latest
      env:
        - name: MODEL_PATH
          value: /models/sd-1.5
        - name: DATASET_PATH
          value: /datasets/train-2025-01
      volumeMounts:
        - name: model-cache
          mountPath: /models
          readOnly: true
        - name: dataset-cache
          mountPath: /datasets
          readOnly: true
      resources:
        requests:
          cpu: "2"
          memory: "8Gi"
        limits:
          cpu: "4"
          memory: "16Gi"
  volumes:
    - name: model-cache
      hostPath:
        path: /mnt/ml-cache/models
        type: Directory
    - name: dataset-cache
      hostPath:
        path: /mnt/ml-cache/datasets
        type: Directory
```

The pod starts immediately — no waiting for model downloads.

### Step 5 — Update cache (e.g., new model version)

Edit `ml-cache-values.yaml` to add a new model or update an existing one:

```yaml
  - name: "llama-3-70b"  # New model
    source: "huggingface"
    ref: "meta-llama/Llama-3-70b"
    version: "2024-06-01"
    destination: "models/llama-3-70b"
```

Redeploy:

```bash
helm upgrade ml-cache oci://ghcr.io/ram-pi/lke-node-cache-manager \
  --version 0.1.0 \
  --namespace node-cache \
  --values ml-cache-values.yaml
```

The DaemonSet automatically rolls, downloads the new model, and garbage-collects any removed assets.

### Monitoring & Alerts

Create Prometheus alerts to monitor cache health:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: ml-cache-alerts
spec:
  groups:
    - name: ml.cache
      rules:
        - alert: CacheDownloadFailures
          expr: rate(cache_download_failure_total[5m]) > 0
          for: 15m
          annotations:
            summary: "Cache downloads failing on {{ $labels.instance }}"

        - alert: LowDiskSpace
          expr: node_disk_free_bytes / node_disk_total_bytes < 0.1
          for: 10m
          annotations:
            summary: "Less than 10% free disk on {{ $labels.instance }}"
```

### Teardown

```bash
helm uninstall ml-cache -n node-cache
make delete-lke CLUSTER_LABEL=ml-cluster
```

---

## Adding more use cases

Other scenarios that follow the same building blocks:

| Use Case | What changes |
|---|---|
| **VPN gateway** | VM runs WireGuard or OpenVPN instead of plain iptables NAT; route injector steers only VPN-bound CIDRs (not `0.0.0.0/0`) |
| **Private service mesh** | Route specific RFC-1918 ranges (e.g. `10.0.0.0/8`) through the VLAN — no default route replacement needed |
| **Multi-cluster east-west** | Two LKE clusters share the same VLAN; route injector on each side points pod CIDRs at the other cluster's gateway node |
| **Egress per namespace** | Deploy multiple `lke-route-injector` releases with different `nodeSelector` values targeting node pools dedicated to specific namespaces |
