"""API gateway routing and policy enforcement."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import HTTPException, Request, Response

from src.api.security import get_identity, subscription_scope, tenant_scope
from src.audit import write_audit_event
from src.reliability import CircuitBreaker, CircuitOpenError
from src.service_contracts.internal import CORRELATION_HEADER, RouteTarget

ROUTES = {
    "auth": RouteTarget("auth_service_url", "/api", requires_subscription=False),
    "tenants": RouteTarget("auth_service_url", "/api", requires_subscription=False),
    "subscriptions": RouteTarget("auth_service_url", "/api", requires_subscription=False),
    "tenant-health": RouteTarget("auth_service_url", "/api", requires_subscription=False),
    "costs": RouteTarget("processing_service_url", "/internal"),
    "resources": RouteTarget("processing_service_url", "/internal"),
    "recommendations": RouteTarget("processing_service_url", "/internal"),
    "chat": RouteTarget("ai_service_url", "/internal"),
    "inventory": RouteTarget("ai_service_url", "/internal"),
    "onboarding": RouteTarget("auth_service_url", "/api", requires_subscription=False),
}

PUBLIC_AUTH_PATHS = {"auth/login", "auth/callback"}


class GatewayApplicationService:
    def __init__(self, app) -> None:
        self.app = app
        app.state.rate_windows = getattr(app.state, "rate_windows", defaultdict(deque))
        app.state.breakers = getattr(app.state, "breakers", defaultdict(CircuitBreaker))
        if not hasattr(app.state, "service_credential"):
            app.state.service_credential = None

    def rate_limit(self, request: Request, subject: str) -> None:
        now = time.monotonic()
        window = request.app.state.rate_windows[subject]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= request.app.state.settings.api_rate_limit_per_minute:
            raise HTTPException(429, "Rate limit exceeded")
        window.append(now)

    def is_public_auth_path(self, path: str) -> bool:
        return path.strip("/") in PUBLIC_AUTH_PATHS

    def upstream_response(self, upstream: httpx.Response) -> Response:
        response = Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )
        location = upstream.headers.get("location")
        if location:
            response.headers["Location"] = location
        for cookie in upstream.headers.get_list("set-cookie"):
            response.headers.append("Set-Cookie", cookie)
        return response

    def internal_authorization_header(self, request: Request) -> str:
        settings = request.app.state.settings
        if not settings.entra_auth_enabled:
            return ""
        if not settings.use_managed_identity:
            now = datetime.now(timezone.utc)
            token = jwt.encode(
                {
                    "iss": "azure-cost-advisor",
                    "aud": settings.internal_api_audience,
                    "iat": now,
                    "exp": now + timedelta(hours=1),
                },
                settings.api_session_secret,
                algorithm="HS256",
            )
            return f"Bearer {token}"

        if request.app.state.service_credential is None:
            from azure.identity import DefaultAzureCredential

            request.app.state.service_credential = DefaultAzureCredential()
        scope = settings.internal_api_audience.rstrip("/") + "/.default"
        try:
            service_token = request.app.state.service_credential.get_token(scope)
            return f"Bearer {service_token.token}"
        except Exception as e:
            import logging

            logging.getLogger("finops.api.audit").error(f"Failed to get token: {e}")
            raise HTTPException(500, f"Token error: {e}") from e

    async def proxy(self, path: str, request: Request):
        root = path.split("/", 1)[0]
        if root not in ROUTES:
            raise HTTPException(404, "Route not found")
        public_auth = self.is_public_auth_path(path)
        identity = None if public_auth else get_identity(request)
        rate_subject = (
            f"{identity.tenant_id}:{identity.user_id}"
            if identity
            else f"anonymous:{request.client.host if request.client else 'unknown'}"
        )
        self.rate_limit(request, rate_subject)
        route = ROUTES[root]
        tenant_id = tenant_scope(request, identity) if identity else ""
        subscription_id = (
            subscription_scope(request, identity, tenant_id)
            if identity and route.requires_subscription
            else request.headers.get("X-Subscription-ID", "")
        )
        target = getattr(request.app.state.settings, route.setting_name)
        upstream_path = f"{route.upstream_prefix}/{path}"
        headers = {CORRELATION_HEADER: request.state.correlation_id}
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if subscription_id:
            headers["X-Subscription-ID"] = subscription_id
        if content_type := request.headers.get("Content-Type"):
            headers["Content-Type"] = content_type
        if route.setting_name == "auth_service_url":
            if authorization := request.headers.get("Authorization"):
                headers["Authorization"] = authorization
            if cookie := request.headers.get("Cookie"):
                headers["Cookie"] = cookie
        elif request.app.state.settings.entra_auth_enabled:
            headers["Authorization"] = self.internal_authorization_header(request)
        body = await request.body()

        async def send():
            async with httpx.AsyncClient(timeout=60) as client:
                return await client.request(
                    request.method,
                    f"{target}{upstream_path}",
                    params=request.query_params,
                    content=body,
                    headers=headers,
                )

        try:
            upstream = await request.app.state.breakers[target].call_async(send)
        except CircuitOpenError as exc:
            raise HTTPException(
                503, "Upstream service temporarily unavailable"
            ) from exc
        if identity:
            write_audit_event(
                request.app.state.storage,
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                user_id=identity.user_id,
                action=f"{request.method} /api/{path}",
                correlation_id=request.state.correlation_id,
                outcome="success" if upstream.status_code < 400 else "failure",
                details={"statusCode": upstream.status_code, "upstream": target},
            )
        return self.upstream_response(upstream)
