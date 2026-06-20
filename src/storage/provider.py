"""Repository bundle used by application composition roots."""

from dataclasses import dataclass

from src.repositories.interfaces import (
    CostFactRepository,
    ProcessingMetadataRepository,
    RawPayloadRepository,
    RecommendationRepository,
    ResourceRepository,
    SubscriptionRepository,
    TenantRepository,
    TenantHealthRepository,
    TenantUserRepository,
    SessionRepository,
)


@dataclass(frozen=True)
class StorageProvider:
    tenants: TenantRepository
    subscriptions: SubscriptionRepository
    tenant_users: TenantUserRepository
    tenant_health: TenantHealthRepository
    raw_payloads: RawPayloadRepository
    cost_facts: CostFactRepository
    resources: ResourceRepository
    recommendations: RecommendationRepository
    processing_metadata: ProcessingMetadataRepository
    sessions: SessionRepository
