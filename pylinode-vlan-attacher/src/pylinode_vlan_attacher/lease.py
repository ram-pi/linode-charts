"""Kubernetes Lease leader election for active/standby mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from kubernetes import client
from kubernetes.client.exceptions import ApiException


@dataclass
class LeaseManager:
    api: client.CoordinationV1Api
    namespace: str
    lease_name: str
    holder_identity: str
    lease_duration_seconds: int

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def try_acquire_or_renew(self) -> bool:
        now = self._now()
        body = client.V1Lease(
            metadata=client.V1ObjectMeta(name=self.lease_name, namespace=self.namespace),
            spec=client.V1LeaseSpec(
                holder_identity=self.holder_identity,
                lease_duration_seconds=self.lease_duration_seconds,
                renew_time=now,
            ),
        )
        try:
            existing = self.api.read_namespaced_lease(self.lease_name, self.namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise
            self.api.create_namespaced_lease(self.namespace, body)
            return True

        spec = existing.spec or client.V1LeaseSpec()
        holder = spec.holder_identity
        renew_time = spec.renew_time
        duration = spec.lease_duration_seconds or self.lease_duration_seconds

        expired = False
        if holder in (None, ""):
            expired = True
        elif renew_time is not None:
            expired = now > (renew_time + timedelta(seconds=duration))

        if holder not in (None, "", self.holder_identity) and not expired:
            return False

        body.metadata.resource_version = existing.metadata.resource_version
        self.api.replace_namespaced_lease(self.lease_name, self.namespace, body)
        return True

    def current_holder(self) -> str:
        """Return current lease holder identity, if any."""
        lease = self.api.read_namespaced_lease(self.lease_name, self.namespace)
        spec = lease.spec or client.V1LeaseSpec()
        return spec.holder_identity or ""
