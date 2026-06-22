from __future__ import annotations

import os
from uuid import uuid4

import pytest
import requests
from azure.identity import DefaultAzureCredential

from src.ai.embeddings import build_embeddings
from src.config import Settings
from src.events.bus import AzureServiceBusPublisher
from src.events.contracts import EventType, PlatformEvent
from src.onboarding.azure_access import AzureAccessClient
from src.search.azure_ai_search import AzureAISearchProvider
from src.storage.factory import create_storage_provider


pytestmark = pytest.mark.live_azure


def _settings() -> Settings:
    if os.getenv("RUN_LIVE_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("RUN_LIVE_INTEGRATION_TESTS=true is required")
    return Settings()


def test_entra_openid_metadata_is_reachable():
    settings = _settings()
    assert settings.entra_client_id
    response = requests.get(
        f"{settings.entra_authority.rstrip('/')}/v2.0/.well-known/openid-configuration",
        timeout=30,
    )
    response.raise_for_status()
    assert response.json()["authorization_endpoint"]


def test_cosmos_and_blob_connectivity():
    settings = _settings()
    assert settings.storage_provider == "cosmos"
    storage = create_storage_provider(settings)
    storage.tenants.container.read()
    storage.raw_payloads.container.get_container_properties()


def test_service_bus_publish():
    settings = _settings()
    publisher = AzureServiceBusPublisher(settings)
    publisher.publish(
        PlatformEvent(
            eventType=EventType.HEALTH_CHECK_FAILED,
            tenantId="release-validation",
            correlationId=str(uuid4()),
            producer="release-integration-test",
            payload={"operation": "service_bus_connectivity"},
        )
    )


def test_ai_search_index_and_openai_embedding():
    settings = _settings()
    search = AzureAISearchProvider(settings)
    search.ensure_index()
    assert search.index_client.get_index(settings.azure_search_index_name)
    vector = build_embeddings(settings).embed_query(
        "release readiness connectivity check"
    )
    assert len(vector) == settings.azure_search_vector_dimensions


def test_delegated_subscription_discovery_and_rbac():
    _settings()
    token = os.getenv("AZURE_DELEGATED_ACCESS_TOKEN", "")
    if not token:
        pytest.skip("AZURE_DELEGATED_ACCESS_TOKEN is required")
    client = AzureAccessClient(token)
    subscriptions = client.discover_subscriptions()
    assert subscriptions
    checks = client.validate_subscription(subscriptions[0].subscription_id)
    assert checks["authentication"].status == "passed"
    assert checks["subscriptionAccess"].status == "passed"
    assert checks["costManagement"].status == "passed"
    assert checks["resourceGraph"].status == "passed"
    assert checks["advisor"].status == "passed"
    assert checks["monitor"].status == "passed"
