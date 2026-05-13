# universal-lke-vlan-controller

Python-based VLAN controller for both standard and Enterprise LKE clusters.

- Uses the `pylinode-vlan-attacher` controller image.
- Keeps Kubernetes Lease-based leader election (active + standby).
- Runs rolling VLAN attachment one node at a time and waits for `Ready=True`.

## Install

```bash
helm upgrade --install universal-lke-vlan-controller ./charts/universal-lke-vlan-controller \
  --namespace lke-vlan-controller \
  --create-namespace \
  --set vlan.name=<VLAN_LABEL> \
  --set vlan.cidr=<VLAN_CIDR> \
  --set existingSecret=linode-token
```

## Required values

| Parameter | Description |
|---|---|
| `vlan.name` | VLAN label to attach |
| `vlan.cidr` | CIDR to allocate node IPs from |
| `vlan.excludedIPs` | IPs within `vlan.cidr` that must never be assigned |
| `controller.nodeSelector` | Optional node labels map to scope which nodes are managed |
| `linodeToken` or `existingSecret` | Linode API token source |

## Important notes

- Set `deployment.image.repository` and `deployment.image.tag` to your published image.
- `controller.applyChanges=false` runs observe-only mode.
- `controller.applyChanges=true` enables rolling mutations.
- `controller.createNamespaceIfMissing=true` lets the controller create `MY_NAMESPACE` at runtime (requires extra RBAC; normally keep this `false` and rely on Helm namespace creation).
- IP assignment is first-free host order within `vlan.cidr`, excluding existing VLAN-assigned IPs and `vlan.excludedIPs`.
- If the leader pod is scheduled on the node selected for update, the controller cordons that node and deletes its own pod first so a standby can take over, then proceeds with the node reboot in the new leader.
- VLAN presence is checked by VLAN label. If a node already has a different VLAN label attached, the controller still applies the configured `vlan.name` and preserves the existing different-label VLAN interface, which can result in multiple VLAN interfaces on one node.
