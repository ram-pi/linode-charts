# lke-route-injector

Injects static IP routes on every targeted LKE node via a DaemonSet. Routes are re-applied on a configurable interval so they survive node reboots automatically.

Designed for **NAT gateway** and **VPN gateway** use cases where traffic must be steered through a VLAN interface after `lke-vlan-controller` has set up the interface.

---

## How it works

- Runs as a **DaemonSet** — one pod per targeted node, restarted automatically on reboot
- Uses `hostNetwork: true` to share the host network namespace, so `ip route` commands affect the actual node routing table (not a container-local namespace)
- Requires only the `NET_ADMIN` capability — no full privilege needed
- Routes are compiled into a ConfigMap at Helm render time; updating `values.yaml` and running `helm upgrade` automatically restarts the pods via a `checksum` annotation
- `ip route replace` is idempotent: safe to run repeatedly without accumulating duplicate routes

---

## Requirements

- Kubernetes **1.31+**
- Helm **3.x**
- VLAN interface must already be active on the node before routes via that interface will work (deploy after `lke-vlan-controller` completes)

---

## Installation

```bash
helm upgrade --install lke-route-injector charts/lke-route-injector \
  --namespace lke-route-injector \
  --create-namespace \
  --set 'routes[0].network=10.0.0.0/8' \
  --set 'routes[0].gateway=172.20.200.1'
```

### Target specific nodes

Use `deployment.nodeSelector` to restrict which nodes run the DaemonSet pod:

```bash
helm upgrade --install lke-route-injector charts/lke-route-injector \
  --namespace lke-route-injector \
  --create-namespace \
  --set 'routes[0].network=10.0.0.0/8' \
  --set 'routes[0].gateway=172.20.200.1' \
  --set 'deployment.nodeSelector.node-role=worker'
```

Or in `values.yaml`:

```yaml
deployment:
  nodeSelector:
    node-role: worker
```

### Multiple routes

```yaml
# values.yaml
routes:
  - network: 10.0.0.0/8
    gateway: 172.20.200.1
  - network: 192.168.50.0/24
    gateway: 172.20.200.1
```

### Default route (NAT / VPN gateway)

```yaml
routes:
  - network: 0.0.0.0/0
    gateway: 172.20.200.1
```

> **Warning:** Replacing the default route (`0.0.0.0/0`) redirects **all** outbound traffic through the specified gateway. Ensure the gateway node has upstream internet connectivity, otherwise the node will lose access to the Kubernetes API server and external services.

### Follow logs after installation

```bash
# Stream logs from all route-injector pods (one per node)
kubectl logs -n lke-route-injector -l app.kubernetes.io/name=lke-route-injector -f

# Or from a specific pod
kubectl logs -n lke-route-injector <pod-name> -f
```

### From OCI (GHCR)

```bash
helm upgrade --install lke-route-injector \
  oci://ghcr.io/ram-pi/lke-route-injector \
  --namespace lke-route-injector \
  --create-namespace \
  --set 'routes[0].network=10.0.0.0/8' \
  --set 'routes[0].gateway=172.20.200.1'
```

---

## Configuration

| Parameter | Description | Default |
|---|---|---|
| `routes` | **Required.** List of `{network, gateway}` entries to inject | `[]` |
| `interval` | Seconds between route re-apply loops | `60` |
| `deployment.image` | Container image repository/tag/pull policy | `alpine:3.21.3`, `IfNotPresent` |
| `deployment.resources` | Resource requests/limits | `cpu: 10m/50m`, `memory: 64Mi/128Mi` |
| `deployment.nodeSelector` | Restrict which nodes run the DaemonSet pod | `{}` (all nodes) |
| `deployment.tolerations` | Tolerations for the DaemonSet pod | `[]` |
| `namespace.create` | Create the namespace as part of this release | `true` |
| `serviceAccount.create` | Create a ServiceAccount | `true` |
| `commonLabels` | Labels added to all resources | `{}` |
| `commonAnnotations` | Annotations added to all resources | `{}` |

---

## Troubleshooting

**Check DaemonSet status**

```bash
kubectl get ds -n lke-route-injector
kubectl logs -l app.kubernetes.io/name=lke-route-injector -n lke-route-injector
```

**Verify routes on the node**

```bash
# SSH into the node or use a privileged debug pod
ip route show
```

**Route not appearing**

- Confirm `hostNetwork: true` is set in the DaemonSet spec
- Confirm `NET_ADMIN` capability is present
- Check pod logs for `WARN: failed to apply route` lines — the gateway IP must be reachable on a directly connected interface
