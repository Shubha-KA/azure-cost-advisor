"""Pydantic schemas for collector payload validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator


class MockMetadata(BaseModel):
    subscription_id: str = Field(alias="subscriptionId")
    api_version: str = Field(alias="apiVersion")
    dataset_type: str | None = Field(default=None, alias="datasetType")
    query_type: str | None = Field(default=None, alias="queryType")
    generated_at: datetime = Field(alias="generatedAt")
    source: str = "mock"

    model_config = {"populate_by_name": True}


class CostRecord(BaseModel):
    date: str
    resource_id: str = Field(default="", alias="resourceId")
    resource_group: str = Field(alias="resourceGroup")
    service_name: str = Field(alias="serviceName")
    location: str
    cost_amount: float = Field(
        validation_alias=AliasChoices("costAmount", "costUSD"),
        serialization_alias="costAmount",
        ge=0,
    )
    usage_quantity: float = Field(alias="usageQuantity", ge=0)
    currency: str = "USD"
    source_system: str = Field(default="Azure Cost Management", alias="sourceSystem")
    source_timestamp: datetime = Field(
        default_factory=datetime.utcnow, alias="sourceTimestamp"
    )
    collection_run_id: str = Field(default="legacy", alias="collectionRunId")
    meter_category: str | None = Field(default=None, alias="meterCategory")
    tags: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")
        return v


class CostDataPayload(BaseModel):
    metadata: MockMetadata
    records: list[CostRecord]


class MetricValues(BaseModel):
    average: float
    maximum: float
    minimum: float
    unit: str


class VmMetricResource(BaseModel):
    resource_id: str = Field(alias="resourceId")
    resource_group: str = Field(alias="resourceGroup")
    resource_name: str = Field(alias="resourceName")
    location: str
    vm_size: str = Field(alias="vmSize")
    time_range: dict[str, str] = Field(alias="timeRange")
    metrics: dict[str, MetricValues]
    source_system: str = Field(default="Azure Monitor", alias="sourceSystem")
    source_timestamp: datetime = Field(
        default_factory=datetime.utcnow, alias="sourceTimestamp"
    )
    collection_run_id: str = Field(default="legacy", alias="collectionRunId")

    model_config = {"populate_by_name": True}


class VmMetricsPayload(BaseModel):
    metadata: MockMetadata
    resources: list[VmMetricResource]


class UnattachedDisk(BaseModel):
    disk_id: str = Field(alias="diskId")
    resource_group: str = Field(alias="resourceGroup")
    disk_name: str = Field(alias="diskName")
    location: str
    disk_size_gb: int = Field(alias="diskSizeGb", gt=0)
    sku: str
    days_unattached: int = Field(alias="daysUnattached", ge=0)
    monthly_cost_estimate_usd: float = Field(alias="monthlyCostEstimateUsd", ge=0)
    managed_by: str | None = Field(default=None, alias="managedBy")

    model_config = {"populate_by_name": True}


class UnattachedDisksPayload(BaseModel):
    metadata: MockMetadata
    data: list[UnattachedDisk]


class PublicIpRecord(BaseModel):
    name: str
    resource_group: str = Field(alias="resourceGroup")
    location: str
    ip_address: str = Field(alias="ipAddress")
    allocation_method: str = Field(alias="allocationMethod")
    sku: str
    associated: bool
    associated_resource: str | None = Field(default=None, alias="associatedResource")
    monthly_cost_estimate_usd: float = Field(alias="monthlyCostEstimateUsd", ge=0)

    model_config = {"populate_by_name": True}


class PublicIpsPayload(BaseModel):
    metadata: MockMetadata
    public_ips: list[PublicIpRecord] = Field(alias="publicIps")

    model_config = {"populate_by_name": True}


class AksNodePool(BaseModel):
    name: str
    vm_size: str = Field(alias="vmSize")
    node_count: int = Field(alias="nodeCount", ge=0)
    avg_cpu_percent: float = Field(alias="avgCpuPercent", ge=0, le=100)
    avg_memory_percent: float = Field(alias="avgMemoryPercent", ge=0, le=100)

    model_config = {"populate_by_name": True}


class AksClusterMetrics(BaseModel):
    resource_id: str = Field(default="", alias="resourceId")
    cluster_name: str = Field(alias="clusterName")
    resource_group: str = Field(alias="resourceGroup")
    location: str
    kubernetes_version: str = Field(alias="kubernetesVersion")
    node_pools: list[AksNodePool] = Field(alias="nodePools")
    metrics: dict[str, float]
    monthly_cost_estimate_usd: float = Field(alias="monthlyCostEstimateUsd", ge=0)
    source_system: str = Field(default="Azure Monitor", alias="sourceSystem")
    source_timestamp: datetime = Field(
        default_factory=datetime.utcnow, alias="sourceTimestamp"
    )
    collection_run_id: str = Field(default="legacy", alias="collectionRunId")

    model_config = {"populate_by_name": True}


class AksMetricsPayload(BaseModel):
    metadata: MockMetadata
    clusters: list[AksClusterMetrics]


class AdvisorRecommendation(BaseModel):
    recommendation_id: str = Field(alias="recommendationId")
    category: str
    impact: str
    impacted_field: str = Field(alias="impactedField")
    problem: str
    solution: str
    resource_id: str = Field(alias="resourceId")
    resource_group: str = Field(alias="resourceGroup")
    resource_name: str = Field(alias="resourceName")
    monthly_savings_usd: float = Field(alias="monthlySavingsUsd", ge=0)
    last_updated: str = Field(alias="lastUpdated")
    source_system: str = Field(default="Azure Advisor", alias="sourceSystem")
    source_timestamp: datetime = Field(
        default_factory=datetime.utcnow, alias="sourceTimestamp"
    )

    model_config = {"populate_by_name": True}


class AdvisorRecommendationsPayload(BaseModel):
    metadata: MockMetadata
    recommendations: list[AdvisorRecommendation]


class ResourceGraphRow(BaseModel):
    id: str
    name: str
    type: str
    resource_group: str = Field(alias="resourceGroup")
    location: str
    properties: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class ResourceGraphPayload(BaseModel):
    metadata: MockMetadata
    data: list[ResourceGraphRow]
