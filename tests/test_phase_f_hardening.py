from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from src.compliance.lifecycle import TenantLifecycleService
from src.collector.run import OrchestrationReport
from src.domain.context import OperationContext
from src.domain.models import CostFact, Tenant
from src.events.bus import InMemoryEventBus, process_message
from src.events.contracts import EventType, PlatformEvent
from src.microservices import collection_service
from src.microservices import gateway_service
from src.microservices import processing_service
from src.reliability import CircuitBreaker, CircuitOpenError
from src.storage.factory import create_storage_provider


def _event():
    return PlatformEvent(
        eventType=EventType.COLLECTION_COMPLETED,
        tenantId="tenant-a",
        subscriptionId="subscription-a",
        collectionRunId="collection-a",
        processingRunId="processing-a",
        correlationId="correlation-a",
        producer="test",
    )


def test_event_contract_and_in_memory_delivery():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(EventType.COLLECTION_COMPLETED.value, received.append)
    bus.publish(_event())
    assert received[0].tenant_id == "tenant-a"
    assert received[0].schema_version == 1


def test_poison_message_is_dead_lettered():
    calls = []
    receiver = SimpleNamespace(
        complete_message=lambda message: calls.append("complete"),
        abandon_message=lambda message: calls.append("abandon"),
        dead_letter_message=lambda message, **kwargs: calls.append("dead-letter"),
    )
    message = SimpleNamespace(delivery_count=5)
    message.__str__ = lambda self: "invalid"
    process_message(receiver, message, lambda event: None, max_attempts=5)
    assert calls == ["dead-letter"]


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)
    operation = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    with pytest.raises(RuntimeError):
        breaker.call(operation)
    with pytest.raises(RuntimeError):
        breaker.call(operation)
    with pytest.raises(CircuitOpenError):
        breaker.call(operation)


@pytest.mark.anyio
async def test_async_circuit_breaker_tracks_awaited_failures():
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=60)

    async def operation():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await breaker.call_async(operation)
    with pytest.raises(CircuitOpenError):
        await breaker.call_async(operation)


def test_gateway_login_is_public_and_propagates_redirect_and_cookies(
    test_settings, monkeypatch
):
    test_settings.auth_mode = "entra"
    test_settings.auth_service_url = "http://auth-service"
    app = gateway_service.app
    app.state.settings = test_settings
    app.state.storage = create_storage_provider(test_settings)
    app.state.rate_windows.clear()
    app.state.breakers.clear()
    captured = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            headers = httpx.Headers(
                [
                    ("location", "https://login.microsoftonline.com/authorize"),
                    ("set-cookie", "finops_auth_flow=flow-a; Path=/; HttpOnly"),
                    ("set-cookie", "nonce=nonce-a; Path=/; HttpOnly"),
                ]
            )
            return httpx.Response(307, headers=headers)

    monkeypatch.setattr(gateway_service.httpx, "AsyncClient", lambda **_: _Client())
    client = TestClient(app, follow_redirects=False)
    response = client.get(
        "/api/auth/login",
        headers={"Cookie": "browser-cookie=value"},
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "https://login.microsoftonline.com/"
    )
    assert len(response.headers.get_list("set-cookie")) == 2
    assert captured["headers"]["Cookie"] == "browser-cookie=value"


def test_collection_service_passes_configured_azure_credential(monkeypatch):
    credential = object()
    captured = {}
    collection_service.app.state.credential_factory = SimpleNamespace(
        for_subscription=lambda tenant_id, subscription_id: credential
    )

    def fake_run_all(**kwargs):
        captured.update(kwargs)
        return OrchestrationReport(
            started_at="2026-06-12T00:00:00Z",
            errors=[],
            results=[],
        )

    monkeypatch.setattr(collection_service, "run_all", fake_run_all)
    result = collection_service._collect_subscription(
        collection_service.app,
        {"tenantId": "tenant-a", "subscriptionId": "subscription-a"},
    )

    assert captured["credential"] is credential
    assert result["errors"] == []


def test_processing_service_exposes_cost_analytics(test_settings):
    test_settings.auth_mode = "legacy"
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    storage.cost_facts.upsert_many(
        "tenant-a",
        [
            CostFact(
                **context.document_fields(),
                date="2026-06-12",
                serviceName="Storage",
                resourceGroup="rg-a",
                costAmount=12.5,
                currency="INR",
                sourceSystem="Azure Cost Management",
                sourceTimestamp="2026-06-12T00:00:00Z",
            )
        ],
    )
    app = processing_service.app
    app.state.settings = test_settings
    app.state.storage = storage
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant-a",
        "X-Subscription-ID": "subscription-a",
    }

    trends = client.get("/internal/costs/trends", headers=headers)
    services = client.get("/internal/costs/services", headers=headers)

    assert trends.status_code == 200
    assert trends.json()[0]["currency"] == "INR"
    assert services.json()[0]["service_name"] == "Storage"
    assert services.json()[0]["costAmount"] == 12.5


def test_tenant_deletion_request_and_execution(test_settings):
    storage = create_storage_provider(test_settings)
    storage.tenants.upsert(
        "tenant-a",
        Tenant(tenantId="tenant-a", correlationId="correlation-a"),
    )
    class _Search:
        def delete_tenant(self, tenant_id):
            assert tenant_id == "tenant-a"
            return 4

    lifecycle = TenantLifecycleService(
        test_settings, storage, search_provider=_Search()
    )
    request = lifecycle.request_deletion("tenant-a", "user-a")
    result = lifecycle.execute_deletion("tenant-a")
    assert request["status"] == "pending"
    assert result["status"] == "deleted"
    assert result["deletedSearchDocuments"] == 4
    assert storage.tenants.get("tenant-a") is None
    tombstones = storage.processing_metadata.list_latest(
        "platform-audit", "tenant-lifecycle"
    )
    assert tombstones[0]["metadataType"] == "tenantDeletionCompleted"
    assert "tenantHash" in tombstones[0]
