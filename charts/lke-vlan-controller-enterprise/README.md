# lke-vlan-controller-enterprise

Variant of [lke-vlan-controller](../lke-vlan-controller/) designed for **LKE Enterprise** clusters, which use VPC-based networking instead of direct public interfaces.

- **Deployment** — multiple replicas are supported for hot-standby failover, but leader election still serialises VLAN attachment so only one pod actively processes nodes at a time
- **Shutdown-before-update** — shuts the Linode down before calling `config-update`, required on LKE Enterprise because the VPC interface is always active
- **Network Helper preserved** — the controller preserves the Linode Network Helper and ensures IPv6 SLAAC and VLAN configuration remain functional. The controller may set `ipv6.is_public = true` for the VPC interface when necessary to retain routable IPv6 addresses used by the kubelet and control-plane reachability.
- **Rolling reboot** — uses `linode-cli linodes boot` (not `reboot`) since the node is already offline; waits until the node shows `Ready=true` before touching the next node

> The chart **does not create** the VLAN itself. Create the VLAN in the Linode Cloud Manager (or via `linode-cli networking vlans create`) and provide its label + CIDR via `values.yaml`.

---

## Requirements

### 1. Linode API token

Create a Personal Access Token in the [Linode Cloud Manager](https://cloud.linode.com/profile/tokens) with the following scope:

| Scope | Access |
|---|---|
| **Linodes** | Read/Write |

The token needs enough privileges to list configs, update configs, shut down, and boot Linodes.

### 2. Existing VLAN + CIDR

The VLAN already exists in the target region. You will supply:

1. The VLAN label (e.g. `my-private-vlan`).
2. The CIDR block whose addresses should be assigned to cluster nodes (e.g. `192.168.128.0/17`).

### 3. LKE Enterprise cluster

- LKE **Enterprise** tier (created via `make create-lke-enterprise` or the Linode Cloud Manager)
- Helm **3.x**
- The controller pod needs outbound access to Linode's API (https://api.linode.com)

---

## Installation

```bash
helm upgrade --install lke-vlan-controller oci://ghcr.io/ram-pi/lke-vlan-controller-enterprise \
  --version 0.2.2 \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=<VLAN_LABEL> \
  --set vlan.cidr=<VLAN_CIDR> \
  --set linodeToken=<YOUR_LINODE_TOKEN>
```

Use an existing Secret instead of `linodeToken`:

```bash
kubectl create secret generic linode-token \
  --namespace lke-vlan-controller \
  --from-literal=token=<YOUR_LINODE_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install lke-vlan-controller oci://ghcr.io/ram-pi/lke-vlan-controller-enterprise \
  --version 0.2.2 \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=<VLAN_LABEL> \
  --set vlan.cidr=<VLAN_CIDR> \
  --set existingSecret=linode-token \
  --set namespace.create=false
```

---

## Configuration

| Parameter | Description | Default |
|---|---|---|
| `vlan.name` | **Required.** VLAN label to attach | `""` |
| `vlan.cidr` | **Required.** CIDR to allocate IPs from | `""` |
| `vlan.excludedIPs` | IPs within the CIDR that the controller must never assign | `[]` |
| `linodeToken` | Inline Linode API token; mutually exclusive with `existingSecret` | `""` |
| `existingSecret` | Name of a pre-existing Secret that holds the token | `""` |
| `secretKey` | Key within the Secret that stores the token | `token` |
| `deployment.replicas` | Number of controller replicas; only the leader is active | `2` |
| `deployment.image` | Controller image repository/tag/pull policy | `alpine:3.21.3`, `IfNotPresent` |
| `deployment.resources` | Resource requests/limits for the controller pod | `cpu: 50m / 200m`, `memory: 64Mi / 128Mi` |
| `deployment.nodeSelector` | Node selector for the controller pod | `{}` |
| `deployment.tolerations` | Tolerations for the controller pod | `[]` |
| `boot.enabled` | Boot each Linode after VLAN attachment | `true` |
| `boot.waitTimeoutSeconds` | Seconds to wait for the node to return to Ready after boot | `600` |
| `boot.drain.enabled` | Evict non-DaemonSet pods before shutdown | `true` |
| `boot.drain.timeoutSeconds` | Seconds to wait for drain completion before proceeding | `120` |
| `exclusion.labelKey` | Label key that marks a node as excluded from VLAN assignment; set to `""` to disable | `lke-vlan-exclude` |
| `serviceAccount.create` | Create a ServiceAccount for the controller | `true` |
| `leaderElection.leaseDurationSeconds` | Seconds a Lease is valid without renewal; standby takes over after expiry | `30` |
| `leaderElection.renewIntervalSeconds` | How often the leader renews the Lease | `10` |
| `commonLabels` | Labels added to all resources | `{}` |
| `commonAnnotations` | Annotations added to all resources | `{}` |

When `deployment.replicas > 1`, the chart also renders a PodDisruptionBudget with `minAvailable: 1`. Single-replica installs intentionally omit the PDB so voluntary disruptions remain possible during maintenance.

---

## How it works

1. **Node inventory** – the controller lists all nodes via the Kubernetes API and finds the matching Linode instance by label.
2. **Interface detection** – it reads the Linode config and skips nodes that already have a VLAN interface with the configured label.
3. **Region-wide IP tracking** – it calls `https://api.linode.com/v4beta/networking/vlans`, gathers every `ipam_address` already assigned to that VLAN, and writes them to a temp file.
4. **Serialised attachment** – for each pending node it:
   - picks the first free IP from the configured CIDR (using `nmap -sL`) and records it in the temp file to avoid intra-loop collisions
   - cordons the node and shuts down the Linode (required on LKE Enterprise while a VPC interface is active)
    - waits for the Linode to be `offline`, then calls `config-update` with the VLAN interface added while preserving Network Helper behaviour and explicitly ensuring the VPC interface IPv6 is left routable when required.
   - labels the node `vlan-ip=<IP>_<prefix>` and annotates it `reboot-pending=true`
   - if the controller pod is on the target node, evicts itself first so it reschedules before shutdown
   - boots the Linode and waits until the node reports `Ready=true` before moving to the next node
   - loops every 60 seconds, re-checking until every node has the interface

All API calls use `linode-cli` with the token supplied via a Kubernetes Secret; the controller adds the VLAN interface only once per node.

The chart renders a PodDisruptionBudget only when `deployment.replicas > 1`. This keeps voluntary disruptions possible for intentionally single-replica installs while still protecting HA standby deployments.

---

## Troubleshooting

**Controller pod crash loops**

```bash
kubectl logs -l app.kubernetes.io/name=lke-vlan-controller -n lke-vlan-controller
```

Common causes:

- Missing `vlan.name` or `vlan.cidr` (the chart fails to render explicitly)
- Linode token lacks Linodes scope or is invalid
- Linode config update fails — inspect the logs for the `linode-cli` error output

**Verify VLAN assignment via `linode-cli`**

```bash
linode-cli linodes configs-list <LINODE_ID>
```

Confirm the output includes an interface with `purpose: vlan`, `label: <VLAN_NAME>`, and the assigned `ipam_address`. Also confirm `helpers.network` is `true` (Network Helper must remain enabled) and that the VPC interface IPv6 block lists `slaac` and `ipv6.is_public=true` when the node requires routable IPv6.
