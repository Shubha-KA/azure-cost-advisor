from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.security import SESSION_COOKIE, SessionTokenService
from src.domain.context import OperationContext
from src.domain.models import AzureSubscription, CostFact, ResourceFact, Tenant
from src.storage.factory import create_storage_provider


class _Inventory:
    def __init__(self, settings, tenant_id, subscription_ids):
        self.tenant_id = tenant_id
        self.subscription_ids = subscription_ids

    def query(self, question):
        return {
            "source": "Azure Resource Graph",
            "timestamp": "2026-06-12T00:00:00Z",
            "subscription_scope": self.subscription_ids,
            "result_count": 1,
            "records": [{"name": "vm-live", "type": "vm"}],
        }


class _Advisor:
    def __init__(self, settings, tenant_id, subscription_ids):
        self.tenant_id = tenant_id
        self.subscription_ids = subscription_ids

    def ask(self, question, history=""):
        return f"{self.tenant_id}:{self.subscription_ids[0]}:{question}"


def _seed(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.api_session_secret = "test-secret-with-enough-entropy"
    storage = create_storage_provider(test_settings)
    storage.tenants.upsert(
        "tenant-a",
        Tenant(
            tenantId="tenant-a",
            displayName="Tenant A",
            correlationId="correlation-a",
        ),
    )
    for tenant_id, subscription_id in (
        ("tenant-a", "subscription-a"),
        ("tenant-b", "subscription-b"),
    ):
        storage.subscriptions.upsert(
            tenant_id,
            AzureSubscription(
                tenantId=tenant_id,
                subscriptionId=subscription_id,
                selected=True,
                correlationId=f"correlation-{tenant_id}",
            ),
        )
        context = OperationContext.create(tenant_id, subscription_id)
        storage.cost_facts.upsert_many(
            tenant_id,
            [
                CostFact(
                    **context.document_fields(),
                    date="2026-06-12",
                    serviceName="Virtual Machines",
                    resourceGroup="rg-a",
                    costAmount=125,
                    currency="INR",
                    sourceSystem="Azure Cost Management",
                    sourceTimestamp="2026-06-12T00:00:00Z",
                )
            ],
        )
        storage.resources.upsert_many(
            tenant_id,
            [
                ResourceFact(
                    **context.document_fields(),
                    resourceId=f"/subscriptions/{subscription_id}/vm-a",
                    resourceName="vm-a",
                    resourceType="microsoft.compute/virtualmachines",
                    resourceGroup="rg-a",
                    sourceSystem="Azure Resource Graph",
                    sourceTimestamp="2026-06-12T00:00:00Z",
                )
            ],
        )
    return storage


def _session(test_settings, tenant_id="tenant-a"):
    return SessionTokenService(test_settings).issue(
        {
            "tid": tenant_id,
            "oid": "user-a",
            "email": "user@example.com",
            "name": "Test User",
            "roles": ["tenant_admin"],
        }
    )


def test_api_auth_dashboard_and_tenant_isolation(test_settings):
    storage = _seed(test_settings)
    client = TestClient(
        create_app(
            test_settings,
            storage=storage,
            inventory_factory=_Inventory,
            advisor_factory=_Advisor,
        )
    )
    client.cookies.set(SESSION_COOKIE, _session(test_settings))
    headers = {
        "X-Tenant-ID": "tenant-a",
        "X-Subscription-ID": "subscription-a",
        "X-Correlation-ID": "request-a",
    }

    me = client.get("/api/auth/me")
    costs = client.get("/api/costs/summary", headers=headers)
    resources = client.get("/api/resources", headers=headers)
    inventory = client.get("/api/inventory/vms", headers=headers)
    chat = client.post("/api/chat", headers=headers, json={"message": "cost?"})

    assert me.status_code == 200
    assert costs.json()["totals"] == [{"currency": "INR", "amount": 125.0}]
    assert costs.headers["X-Correlation-ID"] == "request-a"
    assert resources.json()[0]["tenantId"] == "tenant-a"
    assert inventory.json()["source"] == "Azure Resource Graph"
    assert chat.json()["answer"] == "tenant-a:subscription-a:cost?"

    denied = client.get(
        "/api/costs/summary",
        headers={
            "X-Tenant-ID": "tenant-b",
            "X-Subscription-ID": "subscription-b",
        },
    )
    assert denied.status_code == 403


def test_api_rejects_unselected_subscription(test_settings):
    storage = _seed(test_settings)
    client = TestClient(create_app(test_settings, storage=storage))
    client.cookies.set(SESSION_COOKIE, _session(test_settings))
    response = client.get(
        "/api/resources",
        headers={
            "X-Tenant-ID": "tenant-a",
            "X-Subscription-ID": "subscription-b",
        },
    )
    assert response.status_code == 403


def test_legacy_csv_resource_values_are_json_safe(test_settings):
    test_settings.auth_mode = "legacy"
    test_settings.data_processed_dir = str(
        test_settings.project_root / "data" / "processed"
    )
    test_settings.default_tenant_id = "legacy-tenant"
    test_settings.default_subscription_id = "legacy-subscription"
    client = TestClient(create_app(test_settings))

    response = client.get("/api/resources")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
