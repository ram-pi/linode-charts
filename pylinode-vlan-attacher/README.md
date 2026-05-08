# pylinode-vlan-attacher

Python controller prototype for `lke-vlan-controller-enterprise` logic using Kubernetes API + Linode API (`linode_api4`).

It supports active/standby operation with a Kubernetes `Lease`:
- leader acquires/renews `LEASE_NAME` and runs reconcile loop
- standby instances keep polling the lease and take over on expiry
- leader is sticky: standby does not preempt a healthy leader

## Local run

Prereqs:
- Python managed by `uv`
- kubeconfig pointing to the target cluster
- Linode personal access token with Linodes read/write

Install deps:

```bash
uv sync
```

Run with environment variables:

```bash
export LINODE_TOKEN="<token>"
export VLAN_NAME="my-private-vlan"
export VLAN_CIDR="10.100.100.0/24"
export EXCLUDED_IPS="10.100.100.1 10.100.100.2"
export MY_NAMESPACE="lke-vlan-controller"
# Optional; defaults to local-dev-<pid>
export MY_POD_NAME="local-dev-1"
export LEASE_NAME="pylinode-vlan-attacher-leader"
export LEASE_DURATION_SECONDS="30"
export RENEW_INTERVAL_SECONDS="10"
export POLL_INTERVAL_SECONDS="60"
export APPLY_CHANGES="false"

uv run pylinode-vlan-attacher
```

If the namespace does not exist, create it first:

```bash
kubectl create namespace lke-vlan-controller
```

To simulate standby mode locally, open a second terminal with a different `MY_POD_NAME` and run the same command. One process should log `leader mode`, the other `standby mode`.

## Docker

Image version is sourced from `pylinode-vlan-attacher/VERSION` in CI. The GitHub Actions workflow publishes both `:latest` and `:<VERSION>` tags to GHCR.

Build image:

```bash
docker build -t pylinode-vlan-attacher:dev .
```

Run against local kubeconfig:

```bash
docker run --rm -it \
  -e LINODE_TOKEN="<token>" \
  -e VLAN_NAME="my-private-vlan" \
  -e VLAN_CIDR="10.100.100.0/24" \
  -e EXCLUDED_IPS="10.100.100.1 10.100.100.2" \
  -e MY_NAMESPACE="lke-vlan-controller" \
  -e MY_POD_NAME="docker-dev-1" \
  -e LEASE_NAME="pylinode-vlan-attacher-leader" \
  -e LEASE_DURATION_SECONDS="30" \
  -e RENEW_INTERVAL_SECONDS="10" \
  -e POLL_INTERVAL_SECONDS="60" \
  -e APPLY_CHANGES="false" \
  -e KUBECONFIG="/kube/config" \
  -v "$HOME/.kube/config:/kube/config:ro" \
  pylinode-vlan-attacher:dev
```

To test standby with Docker, run a second container with another `MY_POD_NAME` (for example `docker-dev-2`).

## Rolling attach test

1. Start in observe mode and verify pending nodes:

```bash
export APPLY_CHANGES="false"
uv run pylinode-vlan-attacher
```

2. Stop the process, then enable mutation mode:

```bash
export APPLY_CHANGES="true"
uv run pylinode-vlan-attacher
```

3. Watch the logs. The controller processes one node at a time:
- cordon node
- shutdown Linode
- config-update with VLAN interface
- boot Linode
- wait for Kubernetes node `Ready=True`
- label node and uncordon

4. Verify outcomes:

```bash
kubectl get nodes --show-labels | grep vlan-ip
```

## Notes

- IP allocation is first-free host order within `VLAN_CIDR`.
- The allocator excludes IPs already used on the target VLAN and all IPs from `EXCLUDED_IPS`.
- `APPLY_CHANGES=false` is the default and runs observe-only mode (safe for local testing).
- Set `APPLY_CHANGES=true` only when mutation steps are implemented and validated.
- Current implementation supports rolling VLAN attachment with leader election.
- It already uses `client.networking.vlans()` when available, with API fallback for compatibility.
