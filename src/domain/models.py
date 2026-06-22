"""Pydantic models persisted by Phase A repositories."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.ids import deterministic_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ServerSession(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    tenant_id: str = Field(alias="tenantId", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    auth_session: dict[str, Any] = Field(default_factory=dict, alias="authSession")
    expires_at: datetime = Field(alias="expiresAt")
    
    model_config = ConfigDict(populate_by_name=True, extra="allow")



class DomainModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    correlation_id: str = Field(alias="correlationId", min_length=1)
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")


class Tenant(DomainModel):
    tenant_id: str = Field(alias="tenantId", min_length=1)
    display_name: str = Field(default="", alias="displayName")
    status: str = "active"
    onboarding_status: str = Field(default="not_started", alias="onboardingStatus")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")


class AzureSubscription(DomainModel):
    tenant_id: str = Field(alias="tenantId", min_length=1)
    subscription_id: str = Field(alias="subscriptionId", min_length=1)
    display_name: str = Field(default="", alias="displayName")
    status: str = "active"
    selected: bool = False
    onboarding_status: str = Field(default="not_started", alias="onboardingStatus")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")


class TenantUser(DomainModel):
    tenant_id: str = Field(alias="tenantId", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    email: str = ""
    display_name: str = Field(default="", alias="displayName")
    roles: list[str] = Field(default_factory=list)
    status: str = "active"
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")


class TenantHealth(DomainModel):
    tenant_id: str = Field(alias="tenantId", min_length=1)
    subscription_id: str = Field(alias="subscriptionId", min_length=1)
    validation_status: str = Field(alias="validationStatus")
    validation_results: dict[str, Any] = Field(
        default_factory=dict, alias="validationResults"
    )
    last_checked: datetime = Field(default_factory=utc_now, alias="lastChecked")


class OperationalModel(DomainModel):
    tenant_id: str = Field(alias="tenantId", min_length=1)
    subscription_id: str = Field(alias="subscriptionId", min_length=1)
    collection_run_id: str = Field(alias="collectionRunId", min_length=1)
    processing_run_id: str = Field(alias="processingRunId", min_length=1)


class CollectionRun(DomainModel):
    tenant_id: str = Field(alias="tenantId", min_length=1)
    subscription_id: str = Field(alias="subscriptionId", min_length=1)
    collection_run_id: str = Field(alias="collectionRunId", min_length=1)
    processing_run_id: str | None = Field(default=None, alias="processingRunId")
    status: str = "running"
    started_at: datetime = Field(default_factory=utc_now, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    collectors: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    records_collected: int = Field(default=0, alias="recordsCollected")
    errors: list[str] = Field(default_factory=list)


class ProcessingRun(OperationalModel):
    status: str = "running"
    started_at: datetime = Field(default_factory=utc_now, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    counts: dict[str, int] = Field(default_factory=dict)
    record_counts: dict[str, int] = Field(default_factory=dict, alias="recordCounts")
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    reconciliation_status: str = Field(
        default="not_run", alias="reconciliationStatus"
    )
    errors: list[str] = Field(default_factory=list)


class CostFact(OperationalModel):
    fact_id: str = Field(default="", alias="factId")
    date: date
    resource_id: str = Field(default="", alias="resourceId")
    resource_group: str = Field(default="", alias="resourceGroup")
    service_name: str = Field(default="", alias="serviceName")
    location: str = ""
    cost_amount: float = Field(alias="costAmount")
    usage_quantity: float = Field(default=0, alias="usageQuantity")
    currency: str
    source_system: str = Field(alias="sourceSystem")
    source_timestamp: datetime | str = Field(alias="sourceTimestamp")

    @model_validator(mode="after")
    def assign_id(self) -> "CostFact":
        if not self.fact_id:
            self.fact_id = deterministic_id(
                self.tenant_id,
                self.subscription_id,
                self.processing_run_id,
                self.date,
                self.resource_id,
                self.resource_group,
                self.service_name,
                self.location,
                self.currency,
                self.cost_amount,
                self.usage_quantity,
            )
        self.currency = self.currency.upper()
        self.resource_id = self.resource_id.strip().rstrip("/").lower()
        return self


class ResourceFact(OperationalModel):
    resource_fact_id: str = Field(default="", alias="resourceFactId")
    resource_id: str = Field(alias="resourceId", min_length=1)
    resource_name: str = Field(alias="resourceName")
    resource_type: str = Field(alias="resourceType")
    resource_group: str = Field(default="", alias="resourceGroup")
    location: str = ""
    actual_cost_collected_period: float = Field(
        default=0, alias="actualCostCollectedPeriod"
    )
    actual_cost_currency: str = Field(default="", alias="actualCostCurrency")
    estimated_monthly_cost: float = Field(default=0, alias="estimatedMonthlyCost")
    estimated_cost_currency: str = Field(default="", alias="estimatedCostCurrency")
    cost_basis: str = Field(default="unknown", alias="costBasis")
    waste_level: str = Field(default="NONE", alias="wasteLevel")
    recommendation: str = ""
    estimated_savings: float = Field(default=0, alias="estimatedSavings")
    savings_currency: str = Field(default="", alias="savingsCurrency")
    source_system: str = Field(alias="sourceSystem")
    source_timestamp: datetime | str = Field(alias="sourceTimestamp")
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_identity(self) -> "ResourceFact":
        self.resource_id = self.resource_id.strip().rstrip("/").lower()
        if not self.resource_fact_id:
            self.resource_fact_id = deterministic_id(
                self.tenant_id,
                self.subscription_id,
                self.processing_run_id,
                self.resource_id,
            )
        return self


class Recommendation(OperationalModel):
    recommendation_id: str = Field(default="", alias="recommendationId")
    resource_id: str = Field(default="", alias="resourceId")
    category: str = "finops"
    status: str = "active"
    title: str = ""
    content: str
    estimated_savings: float = Field(default=0, alias="estimatedSavings")
    currency: str = ""
    source_system: str = Field(alias="sourceSystem")
    source_timestamp: datetime | str = Field(alias="sourceTimestamp")
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def assign_id(self) -> "Recommendation":
        self.resource_id = self.resource_id.strip().rstrip("/").lower()
        if not self.recommendation_id:
            self.recommendation_id = deterministic_id(
                self.tenant_id,
                self.subscription_id,
                self.processing_run_id,
                self.resource_id,
                self.category,
                self.title,
                self.content,
            )
        self.currency = self.currency.upper()
        return self
