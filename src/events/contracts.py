"""Immutable event envelope shared by independently deployed services."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    TENANT_ONBOARDED = "TenantOnboarded"
    COLLECTION_STARTED = "CollectionStarted"
    COLLECTION_COMPLETED = "CollectionCompleted"
    PROCESSING_STARTED = "ProcessingStarted"
    PROCESSING_COMPLETED = "ProcessingCompleted"
    RECOMMENDATION_GENERATED = "RecommendationGenerated"
    AI_CHAT_EXECUTED = "AIChatExecuted"
    HEALTH_CHECK_FAILED = "HealthCheckFailed"


class PlatformEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()), alias="eventId")
    event_type: EventType = Field(alias="eventType")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="occurredAt"
    )
    tenant_id: str = Field(alias="tenantId", min_length=1)
    subscription_id: str = Field(default="", alias="subscriptionId")
    collection_run_id: str = Field(default="", alias="collectionRunId")
    processing_run_id: str = Field(default="", alias="processingRunId")
    correlation_id: str = Field(alias="correlationId", min_length=1)
    producer: str
    schema_version: int = Field(default=1, alias="schemaVersion")
    attempt: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}
