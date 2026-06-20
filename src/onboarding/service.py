"""Tenant registration, subscription selection, and health orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.auth.entra import AuthSession
from src.domain.models import (
    AzureSubscription,
    Tenant,
    TenantHealth,
    TenantUser,
)
from src.onboarding.azure_access import (
    AzureAccessClient,
    DiscoveredSubscription,
    ValidationCheck,
)
from src.storage.factory import create_storage_provider


class TenantOnboardingService:
    def __init__(self, settings, storage=None, access_client_factory=None) -> None:
        self.settings = settings
        self.storage = storage or create_storage_provider(settings)
        self.access_client_factory = access_client_factory or AzureAccessClient

    def register_authenticated_user(self, session: AuthSession) -> None:
        """Register or update user in their Entra tenant.

        - If the tenant does not exist, auto-create it with onboardingStatus='pending'.
        - The first user in any tenant is assigned the 'tenant_admin' role.
        - Subsequent users receive the 'tenant_user' role.
        Returns True if the tenant is newly created (needs onboarding), False otherwise.
        """
        profile = session.profile
        correlation_id = str(uuid4())
        existing = self.storage.tenants.get(profile.tenant_id)
        is_new_tenant = existing is None
        tenant = Tenant(
            tenantId=profile.tenant_id,
            displayName=(
                existing.display_name
                if existing and existing.display_name
                else profile.display_name or profile.tenant_id
            ),
            status="active" if existing else "pending",
            onboardingStatus=(
                existing.onboarding_status if existing else "not_started"
            ),
            correlationId=correlation_id,
        )
        existing_users = {
            item.user_id: item
            for item in self.storage.tenant_users.list(profile.tenant_id)
        }
        existing_user = existing_users.get(profile.user_id)
        user = TenantUser(
            tenantId=profile.tenant_id,
            userId=profile.user_id,
            email=profile.email,
            displayName=profile.display_name,
            roles=(
                existing_user.roles
                if existing_user
                else ["tenant_admin"]
                if not existing_users
                else ["tenant_user"]
            ),
            status="active",
            correlationId=correlation_id,
        )
        self.storage.tenants.upsert(profile.tenant_id, tenant)
        self.storage.tenant_users.upsert(profile.tenant_id, user)
        return is_new_tenant

    def discover_subscriptions(
        self, session: AuthSession
    ) -> list[DiscoveredSubscription]:
        return self.access_client_factory(
            session.access_token
        ).discover_subscriptions()

    def persist_selected_subscriptions(
        self,
        session: AuthSession,
        discovered: list[DiscoveredSubscription],
        selected_ids: list[str],
    ) -> list[AzureSubscription]:
        available = {item.subscription_id: item for item in discovered}
        unknown = sorted(set(selected_ids).difference(available))
        if unknown:
            raise ValueError(
                f"Selected subscriptions are not accessible: {', '.join(unknown)}"
            )
        entities = []
        for subscription_id in selected_ids:
            item = available[subscription_id]
            entity = AzureSubscription(
                tenantId=session.profile.tenant_id,
                subscriptionId=subscription_id,
                displayName=item.display_name,
                status=item.state,
                selected=True,
                onboardingStatus="validation_pending",
                correlationId=str(uuid4()),
                sourceTenantId=item.tenant_id,
            )
            self.storage.subscriptions.upsert(session.profile.tenant_id, entity)
            entities.append(entity)
        return entities

    def validate_subscriptions(
        self, session: AuthSession, subscription_ids: list[str]
    ) -> list[TenantHealth]:
        client = self.access_client_factory(session.access_token)
        health_records = []
        for subscription_id in subscription_ids:
            checks = client.validate_subscription(subscription_id)
            health = self._health_from_checks(
                session.profile.tenant_id, subscription_id, checks
            )
            self.storage.tenant_health.upsert(
                session.profile.tenant_id, health
            )
            health_records.append(health)
            self._update_subscription_status(session, subscription_id, health)
        return health_records

    def complete_onboarding(
        self, session: AuthSession, subscription_ids: list[str]
    ) -> Tenant:
        health = [
            self.storage.tenant_health.get(
                session.profile.tenant_id, subscription_id
            )
            for subscription_id in subscription_ids
        ]
        if not subscription_ids or any(item is None for item in health):
            raise ValueError("All selected subscriptions must be validated")
        if any(item.validation_status == "failed" for item in health if item):
            raise ValueError(
                "Mandatory Azure access checks must pass before onboarding completes"
            )
        existing = self.storage.tenants.get(session.profile.tenant_id)
        tenant = Tenant(
            tenantId=session.profile.tenant_id,
            displayName=(
                existing.display_name
                if existing
                else session.profile.display_name
            ),
            status="active",
            onboardingStatus="completed",
            correlationId=str(uuid4()),
            completedAt=datetime.now(timezone.utc).isoformat(),
        )
        self.storage.tenants.upsert(session.profile.tenant_id, tenant)
        return tenant

    @staticmethod
    def _health_from_checks(
        tenant_id: str,
        subscription_id: str,
        checks: dict[str, ValidationCheck],
    ) -> TenantHealth:
        mandatory_failed = any(
            check.mandatory and check.status != "passed"
            for check in checks.values()
        )
        optional_failed = any(
            not check.mandatory and check.status != "passed"
            for check in checks.values()
        )
        status = (
            "failed"
            if mandatory_failed
            else "passed_with_warnings"
            if optional_failed
            else "passed"
        )
        return TenantHealth(
            tenantId=tenant_id,
            subscriptionId=subscription_id,
            validationStatus=status,
            validationResults={
                key: value.model_dump(by_alias=True)
                for key, value in checks.items()
            },
            lastChecked=datetime.now(timezone.utc),
            correlationId=str(uuid4()),
        )

    def _update_subscription_status(
        self,
        session: AuthSession,
        subscription_id: str,
        health: TenantHealth,
    ) -> None:
        subscriptions = {
            item.subscription_id: item
            for item in self.storage.subscriptions.list(
                session.profile.tenant_id
            )
        }
        current = subscriptions.get(subscription_id)
        if not current:
            return
        updated = current.model_copy(
            update={
                "onboarding_status": (
                    "validated"
                    if health.validation_status != "failed"
                    else "validation_failed"
                ),
                "correlation_id": str(uuid4()),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.storage.subscriptions.upsert(session.profile.tenant_id, updated)
