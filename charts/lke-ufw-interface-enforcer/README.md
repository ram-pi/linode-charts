# lke-ufw-interface-enforcer

Applies an interface-scoped UFW policy on selected LKE nodes via a DaemonSet.

- **Explicit interface targeting** — enforce directly on a configured interface (for example `eth2`)
- **Interface-scoped inbound policy** — allows only selected inbound port(s) on the target interface
- **Outbound allowed** — keeps outbound traffic allowed so nodes and pods can reach NAT/VPN gateways and receive return traffic
- **Node targeting** — runs only on nodes matching `deployment.nodeSelector` (default `lke-vlan-controller-status=completed`)

---

## Requirements

- Kubernetes **1.31+**
- Helm **3.x**
- Nodes already configured with VLAN interfaces (for example via `lke-vlan-controller` or `lke-vlan-controller-enterprise`)
- The target interface name must be verified in **Linode Cloud Manager** on each node configuration before install

### Verify Interface Name in Linode Cloud Manager

1. Open **Linode Cloud Manager**.
2. Go to **Kubernetes > Your Cluster > Nodes**.
3. Open a node and review **Configuration** details for attached interfaces.
4. Confirm the interface device name used by your VLAN path (for example `eth1` or `eth2`).
5. Set that exact value in `target.interface`.

> This chart runs a privileged DaemonSet with `hostNetwork` + `hostPID` because it modifies host firewall state.

---

## Installation

```bash
helm upgrade --install lke-ufw-interface-enforcer charts/lke-ufw-interface-enforcer \
  --namespace lke-ufw-interface-enforcer \
  --create-namespace \
  --set target.interface=eth2 \
  --set 'policy.inboundRules[0].port=22' \
  --set 'policy.inboundRules[0].protocol=tcp' \
  --set 'policy.inboundRules[1].port=443' \
  --set 'policy.inboundRules[1].protocol=tcp'
```

### Install from GHCR OCI

```bash
helm upgrade --install lke-ufw-interface-enforcer oci://ghcr.io/ram-pi/lke-ufw-interface-enforcer \
  --version 0.3.0 \
  --namespace lke-ufw-interface-enforcer \
  --create-namespace \
  --set target.interface=eth2 \
  --set 'policy.inboundRules[0].port=22' \
  --set 'policy.inboundRules[0].protocol=tcp'
```

### Restrict to a specific node pool

```yaml
# values.yaml
deployment:
  nodeSelector:
    node-type: worker
```

### Values file examples

- Baseline interface policy: `examples/lke-ufw-interface-enforcer.values.yaml`
- LKE Enterprise-focused example: `examples/lke-ufw-interface-enforcer-enterprise.values.yaml`

---

## How it works

1. On each loop, the pod enters the host namespaces via `nsenter`.
2. It uses `target.interface` as the target host interface.
3. It removes previously managed UFW rules.
4. It enforces:
  - inbound allow rules for `policy.inboundRules` on the target interface
  - inbound catch-all deny on target interface (`ufw deny in on <iface>`)
  - outbound allow on target interface (`ufw allow out on <iface>`)
  - logs the active numbered rules with `ufw status numbered`
5. It repeats every `interval` seconds so policy self-heals after node reboot or manual drift.

---

## Configuration

| Parameter | Description | Default |
|---|---|---|
| `target.interface` | Interface to enforce on (for example `eth2`) | `"eth1"` |
| `policy.inboundRules` | Inbound allow-list entries (`port` + `protocol`) on target interface | `[]` |
| `interval` | Seconds between enforcement loops | `60` |
| `deployment.nodeSelector` | Node selector for DaemonSet pods | `lke-vlan-controller-status=completed` |
| `deployment.tolerations` | Tolerations for DaemonSet pods | `[]` |
| `deployment.image` | Image repository/tag/pullPolicy | `alpine:3.21.3`, `IfNotPresent` |
| `deployment.resources` | Pod resources | `cpu: 20m/100m`, `memory: 64Mi/128Mi` |
| `namespace.create` | Create namespace in release | `true` |
| `serviceAccount.create` | Create ServiceAccount | `true` |

---

## Troubleshooting

```bash
# Check DaemonSet rollout
kubectl get ds -n lke-ufw-interface-enforcer

# View enforcer logs
kubectl logs -n lke-ufw-interface-enforcer -l app.kubernetes.io/name=lke-ufw-interface-enforcer -f
```

If logs show `unable to resolve target interface`:

- Confirm `target.interface` exists on target nodes.
- Re-check the interface mapping in Linode Cloud Manager node configuration and ensure the same value is passed in chart values.
- Confirm the target nodes are selected by `deployment.nodeSelector`.

If `kubectl logs` or `kubectl exec` fails with kubelet tunnel errors (for example `No agent available` to `10.x.x.x:10250`), verify the configured target interface is not your cluster control-plane management path. A wrong interface can deny critical node traffic.
