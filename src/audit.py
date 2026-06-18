"""Tenant-scoped immutable audit event persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def write_audit_event(
    storage,
    *,
    tenant_id: str,
    subscription_id: str,
    user_id: str,
    action: str,
    correlation_id: str,
    outcome: str,
    details: dict | None = None,
) -> None:
    storage.processing_metadata.upsert(
        tenant_id,
        {
            "tenantId": tenant_id,
            "subscriptionId": subscription_id or "tenant-scope",
            "metadataType": "auditEvent",
            "metadataId": f"audit-{uuid4()}",
            "userId": user_id,
            "action": action,
            "outcome": outcome,
            "correlationId": correlation_id,
            "occurredAt": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
            "schemaVersion": 1,
        },
    )
