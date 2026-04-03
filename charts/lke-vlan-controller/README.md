# lke-vlan-controller

Deploys a controller that attaches a VLAN interface to every Linode backing an LKE cluster and handles the rolling reboot that activates the interface.

- **Leader election** — Kubernetes Lease-based singleton enforcement: only one pod runs the reconciliation loop at a time; extra replicas wait on standby and take over automatically if the leader crashes
- **Stateless** — derives all state from the Linode API and Kubernetes node labels; safe to restart at any point without manual cleanup
- **Linode CLI only** — every Linode call uses `linode-cli` and preserves all existing config interfaces during the read-modify-write cycle
- **Rolling reboot** — each node is rebooted after its VLAN interface is added and the controller waits until the node shows `Ready=true` before touching the next node
- **Deadlock-free** — the controller's own node is processed last, guaranteeing N-1 schedulable nodes are always available when the pod migrates

> The chart **does not create** the VLAN itself. Create the VLAN in the Linode Cloud Manager (or via `linode-cli networking vlans create`) and provide its label + CIDR via `values.yaml`.

---

## Requirements

### 1. Linode API token

Create a Personal Access Token in the [Linode Cloud Manager](https://cloud.linode.com/profile/tokens) with the following scope:

| Scope | Access |
|---|---|
| **Linodes** | Read/Write |

The token needs enough privileges to list configs, update configs, and reboot Linodes.

### 2. Existing VLAN + CIDR

The VLAN already exists in the target region. You will supply:

1. The VLAN label (e.g. `my-private-vlan`).
2. The CIDR block whose addresses should be assigned to cluster nodes.

> **CIDR recommendation:** Use a range outside `192.168.0.0/16` (Linode Private IP range). `172.20.200.0/24` is a safe, routable choice.

### 3. Kubernetes cluster

- Kubernetes **1.31+**
- Helm **3.x**
- Nodes must have a label that matches the Linode instance label (LKE already provides this)
- The controller pod needs outbound access to Linode's API (https://api.linode.com)

---

## Installation

### From source

```bash
helm upgrade --install lke-vlan-controller charts/lke-vlan-controller \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=my-private-vlan \
  --set vlan.cidr=172.20.200.0/24 \
  --set linodeToken=<YOUR_LINODE_TOKEN>
```

### From OCI (GHCR)

```bash
helm upgrade --install lke-vlan-controller \
  oci://ghcr.io/ram-pi/lke-vlan-controller \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=my-private-vlan \
  --set vlan.cidr=172.20.200.0/24 \
  --set linodeToken=<YOUR_LINODE_TOKEN>
```

### Using an existing Secret

```bash
kubectl create secret generic linode-token \
  --namespace lke-vlan-controller \
  --from-literal=token=<YOUR_LINODE_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install lke-vlan-controller \
  oci://ghcr.io/ram-pi/lke-vlan-controller \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=my-private-vlan \
  --set vlan.cidr=172.20.200.0/24 \
  --set existingSecret=linode-token \
  --set namespace.create=false
```

### Follow logs after installation

```bash
# Identify the leader pod
kubectl get lease -n lke-vlan-controller

# Stream logs from the leader pod
kubectl logs -n lke-vlan-controller -l app.kubernetes.io/name=lke-vlan-controller -f

# Or tail logs from a specific pod
kubectl logs -n lke-vlan-controller <pod-name> -f
```

---

## Configuration

| Parameter | Description | Default |
|---|---|---|
| `vlan.name` | **Required.** VLAN label to attach | `""` |
| `vlan.cidr` | **Required.** CIDR to allocate IPs from | `""` |
| `vlan.excludedIPs` | IPs within the CIDR that the controller must never assign (e.g. gateway, static hosts) | `[]` |
| `linodeToken` | Inline Linode API token; mutually exclusive with `existingSecret` | `""` |
| `existingSecret` | Name of a pre-existing Secret that holds the token | `""` |
| `secretKey` | Key within the Secret that stores the token | `token` |
| `deployment.replicas` | Number of controller replicas; only the leader is active | `2` |
| `deployment.image` | Controller image repository/tag/pull policy | `alpine:3.21.3`, `IfNotPresent` |
| `deployment.resources` | Resource requests/limits for the controller pod | `cpu: 50m / 200m`, `memory: 64Mi / 128Mi` |
| `deployment.nodeSelector` | Node selector for the controller pod | `{}` |
| `deployment.tolerations` | Tolerations for the controller pod | `[]` |
| `reboot.enabled` | Reboot each Linode after VLAN attachment | `true` |
| `reboot.waitTimeoutSeconds` | Seconds to wait for the node to return to Ready after reboot | `600` |
| `exclusion.labelKey` | Label key that marks a node as excluded from VLAN assignment; any non-empty value skips the node; set to `""` to disable | `lke-vlan-exclude` |
| `serviceAccount.create` | Create a ServiceAccount for the controller | `true` |
| `leaderElection.leaseDurationSeconds` | Seconds a Lease is valid without renewal; standby takes over after expiry | `15` |
| `leaderElection.renewIntervalSeconds` | How often the leader renews the Lease | `5` |
| `commonLabels` | Labels added to all resources | `{}` |
| `commonAnnotations` | Annotations added to all resources | `{}` |

---

## Excluding nodes

To prevent the controller from attaching a VLAN interface to specific nodes, label them with `lke-vlan-exclude`:

```bash
# Exclude a single node (useful for testing)
kubectl label node <node-name> lke-vlan-exclude=true

# Remove the exclusion (node will be processed on the next iteration)
kubectl label node <node-name> lke-vlan-exclude-
```

For permanent exclusion of an entire node pool, add the label `lke-vlan-exclude=true` to the node pool in the [Linode Cloud Manager](https://cloud.linode.com) under **Kubernetes → your cluster → Node Pools**. All nodes in the pool will inherit the label automatically.

The label value is not significant — any non-empty value causes the node to be skipped. To disable the feature entirely for all nodes, set `exclusion.labelKey: ""` in `values.yaml`.

---

## How it works

1. **Leader election** – on startup each replica races to acquire a Kubernetes Lease. etcd compare-and-swap ensures exactly one pod becomes leader; the others loop in standby and take over within `leaseDurationSeconds` if the leader crashes.
2. **Node inventory** – the leader lists all nodes via the Kubernetes API and finds the matching Linode instance by label.
3. **Classification** – each node is classified as:
   - `needs_config` — VLAN interface absent from the Linode config
   - `needs_reboot` — VLAN in config, `vlan-ip` label absent from the K8s node
   - `done` — VLAN in config AND `vlan-ip` label present
4. **Region-wide IP tracking** – calls `https://api.linode.com/v4beta/networking/vlans`, gathers every `ipam_address` already assigned to that VLAN, and avoids collisions with VMs outside the cluster.
5. **Serialised attachment** – for each pending node the leader:
   - picks the first free IP from the configured CIDR (using `nmap -sL`)
   - read-modify-writes the Linode config, preserving all existing interfaces
   - (if enabled) reboots the Linode and waits for `Ready=true` before the next node
   - sets the `vlan-ip` label only after the node is back to Ready — this is the stateless completion marker
6. **Deadlock prevention** – the controller's own node is always rebooted last. By the time the pod migrates, all other nodes are Ready and uncordoned.
7. **Lease renewal** – `renew_lease` is called inside every poll loop iteration so the Lease stays alive during long reboot waits. During idle sleep periods between reconcile loops, the leader uses `sleep_renewing` (chunked sleep with renewal every `renewIntervalSeconds`) so the Lease never lapses while the cluster is fully configured.

---

## Observability

The controller sets a `lke-vlan-controller-status` label on each node:

| Value | Meaning |
|---|---|
| `vlan_ip_assigned` | VLAN interface added to Linode config; reboot not yet started |
| `pending_reboot` | Node is being rebooted |
| `completed` | Node rebooted, VLAN active, `vlan-ip` label set |

```bash
kubectl get nodes -L lke-vlan-controller-status,vlan-ip
```

---

## Troubleshooting

**Controller pod crash loops**

```bash
kubectl logs -l app.kubernetes.io/name=lke-vlan-controller -n lke-vlan-controller
```

Common causes:

- Missing `vlan.name` or `vlan.cidr` (the chart fails to render explicitly)
- Linode token lacks Linodes scope or is invalid
- Linode config update fails because the config has unexpected fields — inspect the logs for the `linode-cli` error output

**Check leader election status**

```bash
kubectl get lease -n lke-vlan-controller
```

The `HOLDER` column shows which pod is currently the leader.

**Verify VLAN assignment via `linode-cli`**

```bash
linode-cli linodes configs-list <LINODE_ID>
```

Confirm the output includes an interface with `purpose: vlan`, `label: <VLAN_NAME>`, and the assigned `ipam_address`.
