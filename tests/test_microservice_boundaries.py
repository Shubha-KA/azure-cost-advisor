from __future__ import annotations

import importlib


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
