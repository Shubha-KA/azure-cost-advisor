from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.auth.entra import AuthSession, AuthenticationError, EntraAuthService
from src.onboarding.azure_access import (
    AzureAccessClient,
    DiscoveredSubscription,
    ValidationCheck,
)
from src.onboarding.service import TenantOnboardingService
from src.storage.factory import create_storage_provider


class _FakeMsalClient:
    def initiate_auth_code_flow(self, **kwargs):
        return {"auth_uri": "https://login.example/authorize", "state": "state-a"}

    def acquire_token_by_auth_code_flow(self, flow, params):
        if params.get("state") != flow["state"]:
            raise ValueError("state mismatch")
        return {
            "access_token": "arm-token",
            "expires_in": 3600,
            "id_token_claims": {
                "tid": "tenant-a",
                "oid": "user-a",
                "preferred_username": "user@example.com",
                "name": "Test User",
            },
        }


def _auth_settings(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.entra_client_id = "client-a"
    test_settings.entra_client_secret = "secret-a"
    return test_settings


def _session() -> AuthSession:
    return AuthSession(
        profile={
            "tenantId": "tenant-a",
            "userId": "user-a",
            "email": "user@example.com",
            "displayName": "Test User",
        },
        accessToken="arm-token",
        expiresAt=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )


def test_entra_auth_code_flow_and_profile(test_settings) -> None:
    service = EntraAuthService(
        _auth_settings(test_settings), client=_FakeMsalClient()
    )
    flow = service.begin_login()
    session = service.complete_login(flow, {"code": "code-a", "state": "state-a"})
    assert session.profile.tenant_id == "tenant-a"
    assert session.profile.email == "user@example.com"
    assert session.access_token == "arm-token"
    assert "post_logout_redirect_uri=" in service.logout_url()


def test_entra_rejects_invalid_callback_state(test_settings) -> None:
    service = EntraAuthService(
        _auth_settings(test_settings), client=_FakeMsalClient()
    )
    with pytest.raises(AuthenticationError):
        service.complete_login(
            {"state": "expected"}, {"code": "code-a", "state": "wrong"}
        )


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeHttp:
    @staticmethod
    def get(url, **kwargs):
        return _Response(
            200,
            {
                "value": [
                    {
                        "subscriptionId": "subscription-a",
                        "displayName": "Production",
                        "state": "Enabled",
                        "tenantId": "tenant-a",
                    }
                ]
            },
        )

    @staticmethod
    def request(method, url, **kwargs):
        if "Microsoft.Insights" in url:
            return _Response(403, {"error": {"message": "Forbidden"}})
        return _Response(200, {"value": []})


def test_subscription_discovery_and_required_access(test_settings) -> None:
    client = AzureAccessClient("token", http=_FakeHttp)
    subscriptions = client.discover_subscriptions()
    checks = client.validate_subscription("subscription-a")
    assert subscriptions[0].display_name == "Production"
    assert checks["costManagement"].status == "passed"
    assert checks["resourceGraph"].status == "passed"
    assert checks["monitor"].status == "failed"
    assert checks["monitor"].mandatory is True
    assert checks["advisor"].mandatory is True


class _FakeAccessClient:
    def __init__(self, token):
        self.token = token

    def discover_subscriptions(self):
        return [
            DiscoveredSubscription(
                subscriptionId="subscription-a",
                displayName="Production",
                state="Enabled",
                tenantId="tenant-a",
            )
        ]

    def validate_subscription(self, subscription_id):
        return {
            "authentication": ValidationCheck(
                name="Authentication",
                status="passed",
                mandatory=True,
                message="ok",
            ),
            "subscriptionAccess": ValidationCheck(
                name="Reader",
                status="passed",
                mandatory=True,
                message="ok",
            ),
            "costManagement": ValidationCheck(
                name="Cost",
                status="passed",
                mandatory=True,
                message="ok",
            ),
            "resourceGraph": ValidationCheck(
                name="Graph",
                status="passed",
                mandatory=True,
                message="ok",
            ),
            "advisor": ValidationCheck(
                name="Advisor",
                status="passed",
                mandatory=True,
                message="ok",
            ),
            "monitor": ValidationCheck(
                name="Monitor",
                status="passed",
                mandatory=True,
                message="ok",
            ),
        }


def test_onboarding_persists_user_subscription_and_health(test_settings) -> None:
    service = TenantOnboardingService(
        test_settings,
        access_client_factory=_FakeAccessClient,
    )
    session = _session()
    service.register_authenticated_user(session)
    discovered = service.discover_subscriptions(session)
    service.persist_selected_subscriptions(
        session, discovered, ["subscription-a"]
    )
    health = service.validate_subscriptions(session, ["subscription-a"])
    tenant = service.complete_onboarding(session, ["subscription-a"])

    storage = create_storage_provider(test_settings)
    assert storage.tenant_users.list("tenant-a")[0].roles == ["tenant_admin"]
    assert storage.subscriptions.list("tenant-a")[0].selected is True
    assert health[0].validation_status == "passed"
    assert storage.tenant_health.get(
        "tenant-a", "subscription-a"
    ).validation_status == "passed"
    assert tenant.onboarding_status == "completed"


class _MandatoryFailureClient(_FakeAccessClient):
    def validate_subscription(self, subscription_id):
        checks = super().validate_subscription(subscription_id)
        checks["costManagement"] = ValidationCheck(
            name="Cost",
            status="failed",
            mandatory=True,
            message="Cost Management Reader is missing",
        )
        return checks


def test_onboarding_blocks_missing_mandatory_access(test_settings) -> None:
    service = TenantOnboardingService(
        test_settings,
        access_client_factory=_MandatoryFailureClient,
    )
    session = _session()
    service.register_authenticated_user(session)
    discovered = service.discover_subscriptions(session)
    service.persist_selected_subscriptions(
        session, discovered, ["subscription-a"]
    )
    health = service.validate_subscriptions(session, ["subscription-a"])
    assert health[0].validation_status == "failed"
    with pytest.raises(ValueError, match="Mandatory Azure access"):
        service.complete_onboarding(session, ["subscription-a"])
