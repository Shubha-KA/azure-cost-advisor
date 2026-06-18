"""Internal HTTP contract constants shared by gateway and private services."""

from __future__ import annotations

from dataclasses import dataclass


TENANT_HEADER = "X-Tenant-ID"
SUBSCRIPTION_HEADER = "X-Subscription-ID"
CORRELATION_HEADER = "X-Correlation-ID"


@dataclass(frozen=True)
class ServiceScope:
    tenant_id: str
    subscription_id: str

    @classmethod
    def from_headers(cls, headers) -> "ServiceScope":
        tenant_id = headers.get(TENANT_HEADER, "")
        subscription_id = headers.get(SUBSCRIPTION_HEADER, "")
        if not tenant_id or not subscription_id:
            raise ValueError(f"{TENANT_HEADER} and {SUBSCRIPTION_HEADER} are required")
        return cls(tenant_id=tenant_id, subscription_id=subscription_id)

    def headers(self) -> dict[str, str]:
        return {
            TENANT_HEADER: self.tenant_id,
            SUBSCRIPTION_HEADER: self.subscription_id,
        }


@dataclass(frozen=True)
class RouteTarget:
    setting_name: str
    upstream_prefix: str
    requires_subscription: bool = True
