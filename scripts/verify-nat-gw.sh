#!/bin/sh
# verify-nat-gw.sh — Spin up a debug pod and verify outbound traffic exits via
# the expected NAT gateway IP.
#
# Usage:
#   ./scripts/verify-nat-gw.sh <expected-nat-ip> [namespace]
#
# Arguments:
#   expected-nat-ip   Public IP of the NAT gateway (required)
#   namespace         Namespace to run the debug pod in (default: default)
#
# Examples:
#   ./scripts/verify-nat-gw.sh 45.79.10.1
#   ./scripts/verify-nat-gw.sh 45.79.10.1 lke-route-injector
#
# Requirements:
#   - kubectl configured and pointing at the target cluster
#   - Outbound internet access from pods (port 443 to ifconfig.me)

set -eu

EXPECTED_IP="${1:-}"
NAMESPACE="${2:-default}"
POD_NAME="nat-gw-verify-$$"

if [ -z "$EXPECTED_IP" ]; then
  echo "Usage: $0 <expected-nat-ip> [namespace]"
  exit 1
fi

# Clean up the pod on exit regardless of success or failure.
cleanup() {
  echo "INFO: deleting debug pod $POD_NAME"
  kubectl delete pod "$POD_NAME" -n "$NAMESPACE" --ignore-not-found --wait=false 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "INFO: creating debug pod $POD_NAME in namespace $NAMESPACE"
kubectl run "$POD_NAME" \
  --namespace "$NAMESPACE" \
  --image=curlimages/curl:latest \
  --restart=Never \
  --command -- sleep 120

echo "INFO: waiting for pod to be ready"
kubectl wait pod "$POD_NAME" \
  --namespace "$NAMESPACE" \
  --for=condition=Ready \
  --timeout=60s

echo "INFO: querying ifconfig.me from inside the pod"
ACTUAL_IP=$(kubectl exec "$POD_NAME" -n "$NAMESPACE" -- curl -s --max-time 10 https://ifconfig.me)

echo ""
echo "  Expected NAT gateway IP : $EXPECTED_IP"
echo "  Actual outbound IP      : $ACTUAL_IP"
echo ""

if [ "$ACTUAL_IP" = "$EXPECTED_IP" ]; then
  echo "PASS: outbound traffic is exiting via the NAT gateway ($ACTUAL_IP)"
  exit 0
else
  echo "FAIL: outbound IP does not match the expected NAT gateway"
  echo "      Check that lke-route-injector is running and routes are applied."
  exit 1
fi
