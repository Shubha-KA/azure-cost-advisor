from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt

from src.microservices.common import require_internal
from src.gateway_service.application import GatewayApplicationService


ENTRYPOINTS = {
    "src.microservices.auth_service": "src.auth_service.application",
    "src.microservices.collection_service": "src.collection_service.application",
    "src.microservices.processing_service": "src.processing_service.application",
    "src.microservices.ai_service": "src.ai_service.application",
    "src.microservices.gateway_service": "src.gateway_service.application",
    "src.microservices.notification_service": "src.notification_service.application",
}


def test_microservice_entrypoints_are_http_adapters():
    for entrypoint, application_module in ENTRYPOINTS.items():
        module = importlib.import_module(entrypoint)
        assert hasattr(module, "app")
        assert module.app.state.application.__class__.__module__ == application_module


def test_service_dependency_manifests_exist():
    for name in (
        "auth-service",
        "api-gateway",
        "collection-service",
        "processing-service",
        "ai-service",
        "notification-service",
    ):
        path = f"requirements/services/{name}.txt"
        with open(path, encoding="utf-8") as handle:
            assert handle.read().strip()


def test_internal_hs_token_accepts_configured_audience(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.api_session_secret = "test-secret"
    test_settings.internal_api_audience = "api://internal-services"
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": "azure-cost-advisor",
            "aud": test_settings.internal_api_audience,
            "exp": now + timedelta(minutes=5),
        },
        test_settings.api_session_secret,
        algorithm="HS256",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=test_settings)),
        headers={"Authorization": f"Bearer {token}"},
    )

    claims = require_internal(request)

    assert claims["aud"] == test_settings.internal_api_audience


def test_gateway_uses_hs_internal_token_without_managed_identity(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.use_managed_identity = False
    test_settings.api_session_secret = "test-secret"
    test_settings.internal_api_audience = "api://internal-services"
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=test_settings,
            rate_windows={},
            breakers={},
        )
    )
    service = GatewayApplicationService(app)
    request = SimpleNamespace(app=app)

    authorization = service.internal_authorization_header(request)
    internal_request = SimpleNamespace(
        app=app,
        headers={"Authorization": authorization},
    )

    claims = require_internal(internal_request)

    assert authorization.startswith("Bearer ")
    assert claims["aud"] == test_settings.internal_api_audience
