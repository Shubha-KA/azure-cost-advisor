"""Shared service initialization, probes, and internal authorization."""

from __future__ import annotations

import jwt
from fastapi import FastAPI, HTTPException, Request

from src.api.middleware import ApiMetrics, ObservabilityMiddleware
from src.config import get_settings
from src.observability import configure_observability
from src.storage.factory import create_storage_provider


def service_app(name: str, *, storage=None) -> FastAPI:
    settings = get_settings().model_copy(update={"service_name": name})
    configure_observability(settings)
    app = FastAPI(title=f"Azure Cost Advisor {name}", version="1.0.0")
    app.state.settings = settings
    app.state.storage = storage or create_storage_provider(settings)
    app.state.metrics = ApiMetrics()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/health/live")
    def live():
        return {"status": "alive", "service": name}

    @app.get("/health/ready")
    def ready():
        try:
            if settings.storage_provider == "cosmos":
                app.state.storage.tenants.list()
            return {"status": "ready", "service": name}
        except Exception as exc:
            raise HTTPException(503, f"Dependency unavailable: {exc}") from exc

    return app


def require_internal(request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.entra_auth_enabled:
        return {"appid": "local-development"}
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Service token required")
    token = authorization[7:].strip()
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        tenant_id = str(unverified.get("tid", "organizations"))
        keys = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        )
        signing_key = keys.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.internal_api_audience,
            options={"require": ["exp", "iat", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid service token") from exc
