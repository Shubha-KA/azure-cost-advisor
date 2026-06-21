from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from src.auth.customer_credentials import CustomerTenantCredentialFactory
from src.collector.run import OrchestrationReport
from src.domain.models import AzureSubscription, Tenant
from src.microservices import collection_service
from src.repositories.errors import StorageConfigurationError, TenantScopeError
from src.storage.factory import create_storage_provider


def _seed(storage, tenant_id: str, subscription_id: str, source_tenant: str):
    storage.tenants.upsert(
        tenant_id,
        Tenant(tenantId=tenant_id, correlationId=f"correlation-{tenant_id}"),
    )
    storage.subscriptions.upsert(
        tenant_id,
        AzureSubscription(
            tenantId=tenant_id,
            subscriptionId=subscription_id,
            selected=True,
            onboardingStatus="validated",
            correlationId=f"correlation-{subscription_id}",
            sourceTenantId=source_tenant,
        ),
    )


def test_customer_credential_uses_subscription_authority_tenant(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.use_managed_identity = True
    test_settings.collection_entra_client_id = "collection-app"
    storage = create_storage_provider(test_settings)
    _seed(storage, "platform-tenant-a", "subscription-a", "customer-directory-a")
    calls = []

    def builder(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(authority=kwargs["tenant_id"])

    factory = CustomerTenantCredentialFactory(
        test_settings,
        storage,
        assertion_provider=lambda: "projected-jwt",
        credential_builder=builder,
    )
    credential = factory.for_subscription("platform-tenant-a", "subscription-a")

    assert credential.authority == "customer-directory-a"
    assert calls[0]["client_id"] == "collection-app"
    assert calls[0]["func"]() == "projected-jwt"


def test_customer_credential_rejects_cross_tenant_subscription(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.use_managed_identity = True
    test_settings.collection_entra_client_id = "collection-app"
    storage = create_storage_provider(test_settings)
    _seed(storage, "tenant-a", "subscription-a", "tenant-a")
    factory = CustomerTenantCredentialFactory(
        test_settings,
        storage,
        assertion_provider=lambda: "projected-jwt",
        credential_builder=lambda **kwargs: object(),
    )

    with pytest.raises(TenantScopeError):
        factory.for_subscription("tenant-b", "subscription-a")


def test_missing_collection_app_configuration_fails_closed(test_settings):
    test_settings.auth_mode = "entra"
    storage = create_storage_provider(test_settings)
    _seed(storage, "tenant-a", "subscription-a", "tenant-a")

    with pytest.raises(StorageConfigurationError):
        CustomerTenantCredentialFactory(
            test_settings,
            storage,
        ).for_subscription("tenant-a", "subscription-a")


def test_local_docker_compose_uses_client_secret_credential(test_settings, monkeypatch):
    test_settings.auth_mode = "entra"
    test_settings.use_managed_identity = False
    test_settings.collection_entra_client_id = "collection-app"
    test_settings.azure_client_id = "local-client"
    test_settings.azure_client_secret = "local-secret"
    storage = create_storage_provider(test_settings)
    _seed(storage, "tenant-a", "subscription-a", "customer-directory-a")
    calls = []

    class _ClientSecretCredential:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "azure.identity",
        SimpleNamespace(ClientSecretCredential=_ClientSecretCredential),
    )

    credential = CustomerTenantCredentialFactory(
        test_settings,
        storage,
        assertion_provider=lambda: "should-not-be-read",
    ).for_subscription("tenant-a", "subscription-a")

    assert isinstance(credential, _ClientSecretCredential)
    assert calls == [
        {
            "tenant_id": "customer-directory-a",
            "client_id": "local-client",
            "client_secret": "local-secret",
        }
    ]


def test_local_docker_compose_uses_default_azure_credential_without_workload_identity(
    test_settings, monkeypatch
):
    test_settings.auth_mode = "entra"
    test_settings.use_managed_identity = False
    test_settings.collection_entra_client_id = "collection-app"
    storage = create_storage_provider(test_settings)
    _seed(storage, "tenant-a", "subscription-a", "customer-directory-a")
    calls = []

    class _DefaultAzureCredential:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "azure.identity",
        SimpleNamespace(DefaultAzureCredential=_DefaultAzureCredential),
    )

    credential = CustomerTenantCredentialFactory(
        test_settings,
        storage,
        assertion_provider=lambda: "should-not-be-read",
    ).for_subscription("tenant-a", "subscription-a")

    assert isinstance(credential, _DefaultAzureCredential)
    assert calls == [
        {
            "exclude_workload_identity_credential": True,
            "exclude_managed_identity_credential": True,
        }
    ]


def test_scheduled_collection_uses_distinct_customer_credentials(
    test_settings, monkeypatch
):
    test_settings.auth_mode = "entra"
    storage = create_storage_provider(test_settings)
    _seed(storage, "tenant-a", "subscription-a", "directory-a")
    _seed(storage, "tenant-b", "subscription-b", "directory-b")
    credentials = {
        ("tenant-a", "subscription-a"): object(),
        ("tenant-b", "subscription-b"): object(),
    }
    used = []

    class _Factory:
        def for_subscription(self, tenant_id, subscription_id):
            return credentials[(tenant_id, subscription_id)]

    def fake_run_all(**kwargs):
        used.append(
            (
                kwargs["context"].tenant_id,
                kwargs["context"].subscription_id,
                kwargs["credential"],
            )
        )
        return OrchestrationReport(
            started_at="2026-06-15T00:00:00Z",
            errors=[],
            results=[],
        )

    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=test_settings,
            storage=storage,
            events=SimpleNamespace(publish=lambda event: None),
            credential_factory=_Factory(),
        )
    )
    monkeypatch.setattr(collection_service, "run_all", fake_run_all)

    result = collection_service.run_scheduled_cycle(app)

    assert result == {"subscriptionsAttempted": 2, "failures": 0}
    assert used == [
        ("tenant-a", "subscription-a", credentials[("tenant-a", "subscription-a")]),
        ("tenant-b", "subscription-b", credentials[("tenant-b", "subscription-b")]),
    ]
