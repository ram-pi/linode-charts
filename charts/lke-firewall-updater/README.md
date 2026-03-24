# lke-firewall-updater

Keeps one or more [Linode Cloud Firewalls](https://techdocs.akamai.com/cloud-computing/docs/cloud-firewall) in sync with the public IPs of your LKE nodes.

- **DaemonSet** (`register`) — on each node boot, adds the node's public IP to a named inbound rule in every configured firewall
- **CronJob** (`cleanup`) — runs on a schedule and removes IPs of nodes that no longer exist

The rule is named **`lke-nodes-{cluster_id}`** automatically (using the `lke.k8s.io/cluster-id` label that LKE sets on every node). If the label is absent, it falls back to the `firewall.ruleName` value.

> **This chart does not create the Cloud Firewall.** You must create the firewall before installing the chart and pass its ID in `firewall.ids`.

---

## Requirements

### 1. Linode API token

Create a **Personal Access Token** in the [Linode Cloud Manager](https://cloud.linode.com/profile/tokens) with the following scope:

| Scope | Access |
|---|---|
| **Firewalls** | Read/Write |

No other scopes are needed.

### 2. One or more existing Cloud Firewalls

Create a Cloud Firewall before installing the chart. The chart manages a single **inbound rule entry** within each firewall (named `lke-nodes-{cluster_id}`). All other rules are left untouched.

**Via Linode Cloud Manager:**

1. Go to **Networking → Cloud Firewalls → Create Firewall**
2. Assign a label (e.g. `lke-egress`) and set default policies
3. Note the **Firewall ID** from the URL or the firewall list

**Via `linode-cli`:**

```bash
linode-cli firewalls create \
  --label lke-egress \
  --rules.inbound_policy DROP \
  --rules.outbound_policy ACCEPT

# Note the "id" field in the output
```

> The firewall does not need any pre-existing rules. The chart creates the `lke-nodes-{cluster_id}` rule entry automatically on the first node boot.

### 3. Kubernetes cluster

- Kubernetes **1.31+**
- Helm **3.x**
- Nodes must have `ExternalIP` set in their status addresses (standard on LKE)

---

## Installation

```bash
helm upgrade --install lke-fw-updater charts/lke-firewall-updater \
  --namespace lke-firewall-updater \
  --create-namespace \
  --set-json 'firewall.ids=[12345]' \
  --set linodeToken=<YOUR_LINODE_TOKEN>
```

Multiple firewalls:

```bash
helm upgrade --install lke-fw-updater charts/lke-firewall-updater \
  --namespace lke-firewall-updater \
  --create-namespace \
  --set-json 'firewall.ids=[12345,67890]' \
  --set linodeToken=<YOUR_LINODE_TOKEN>
```

Using an existing Secret instead of `linodeToken`:

```bash
kubectl create secret generic linode-token \
  --namespace lke-firewall-updater \
  --from-literal=token=<YOUR_LINODE_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install lke-fw-updater charts/lke-firewall-updater \
  --namespace lke-firewall-updater \
  --create-namespace \
  --set-json 'firewall.ids=[12345]' \
  --set existingSecret=linode-token \
  --set namespace.create=false
```

---

## Configuration

| Parameter | Description | Default |
|---|---|---|
| `firewall.ids` | **Required.** List of Linode Cloud Firewall IDs | `[]` |
| `firewall.ruleName` | Fallback rule label when cluster ID cannot be auto-detected | `lke-nodes` |
| `firewall.protocol` | Rule protocol | `TCP` |
| `firewall.ports` | Ports expression (Linode format) | `1-65535` |
| `firewall.action` | Rule action: `ACCEPT` or `DROP` | `ACCEPT` |
| `linodeToken` | Linode API token (creates a Secret). Mutually exclusive with `existingSecret` | `""` |
| `existingSecret` | Name of a pre-existing Secret containing the token | `""` |
| `secretKey` | Key within the Secret that holds the token value | `token` |
| `namespace.create` | Create the namespace as part of the Helm release | `true` |
| `daemonset.enabled` | Enable the node-registration DaemonSet | `true` |
| `daemonset.image.tag` | DaemonSet image tag | `3.21.3` |
| `daemonset.tolerations` | Tolerations (e.g. to run on control-plane nodes too) | `[]` |
| `cronjob.enabled` | Enable the periodic cleanup CronJob | `true` |
| `cronjob.schedule` | Cron schedule for the cleanup job | `*/15 * * * *` |
| `cronjob.image.tag` | CronJob image tag | `3.21.3` |
| `serviceAccount.create` | Create a ServiceAccount | `true` |

---

## How it works

### Node registration (DaemonSet)

When a pod starts on a node it:

1. Queries the Kubernetes API for the node object using the pod's own `NODE_NAME` (via Downward API)
2. Reads the node's `ExternalIP` address and `lke.k8s.io/cluster-id` label
3. Derives the effective rule name: `lke-nodes-{cluster_id}` (or falls back to `firewall.ruleName`)
4. For each firewall ID in `firewall.ids`:
   - Reads the current rules via `GET /v4/networking/firewalls/{id}/rules`
   - Merges the IP (as a `/32` CIDR) into the managed rule, creating the rule entry if absent
   - Writes back via `PUT` — retrying up to 10 times with random jitter (1–10 s) on conflicts
5. Sleeps indefinitely — keeping the DaemonSet pod alive at near-zero CPU

### Stale IP cleanup (CronJob)

Every 15 minutes (by default) the cleanup job:

1. Lists all cluster nodes via the Kubernetes API and collects their `ExternalIP` addresses
2. Detects the LKE cluster ID to derive the same effective rule name
3. For each firewall ID:
   - Reads the current rule from the Linode API
   - Removes any IPs not present in the live node list
   - Writes back only if something changed (no-op if all IPs are still live)

> **Safety guard:** if the Kubernetes API returns no `ExternalIP` addresses (transient failure), the cleanup job exits without making any changes.

### Race condition handling

The Linode Firewall API does not support conditional updates (ETags / CAS). When multiple nodes boot simultaneously they compete on the same read-modify-write. The chart mitigates this with:

- **Random jitter** (1–10 s) before each retry
- **`jq unique`** deduplication — adding the same IP twice is a no-op
- **10 retries max** per firewall

---

## Troubleshooting

**DaemonSet pod in `CrashLoopBackOff`**

```bash
kubectl logs -l app.kubernetes.io/component=register -n lke-firewall-updater
```

Common causes:
- `firewall.ids` contains a wrong ID — verify in the Linode Cloud Manager
- API token missing `Firewalls: Read/Write` scope
- Node has no `ExternalIP` — check `kubectl get nodes -o wide`

**Verify the firewall rule via `linode-cli`**

```bash
linode-cli firewalls rules-list <FIREWALL_ID>
```

**Trigger a manual cleanup run**

```bash
kubectl create job --from=cronjob/lke-fw-updater-lke-firewall-updater-cleanup manual-test \
  -n lke-firewall-updater
kubectl logs -l job-name=manual-test -n lke-firewall-updater
```
