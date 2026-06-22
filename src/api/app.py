"""FastAPI composition root and tenant-scoped endpoints."""

from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import math
from types import SimpleNamespace
from typing import Any, Callable
import uuid

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.ai.advisor import FinOpsAdvisor
from src.ai.inventory import ResourceGraphInventoryService
from src.auth.customer_credentials import CustomerTenantCredentialFactory
from src.auth.entra import EntraAuthService
from src.config import Settings, get_settings
from src.dashboard.data_loader import DashboardDataLoader
from src.domain.models import ServerSession
from src.onboarding.service import TenantOnboardingService
from src.storage.factory import create_storage_provider

from src.api.middleware import ApiMetrics, ObservabilityMiddleware
from src.api.security import (
    SESSION_COOKIE,
    SessionTokenService,
    get_identity,
    subscription_scope,
    tenant_scope,
)

INVENTORY_QUESTIONS = {
    "resource-groups": "What resource groups do I have?",
    "vms": "What VMs exist?",
    "aks": "What AKS clusters exist?",
    "storage": "Show storage accounts",
    "keyvaults": "Show Key Vaults",
}


def _dump(item) -> dict[str, Any]:
    return item.model_dump(by_alias=True, mode="json")


def _scopes(request: Request) -> tuple[Any, str, str]:
    identity = get_identity(request)
    tenant_id = tenant_scope(request, identity)
    subscription_id = subscription_scope(request, identity, tenant_id)
    return identity, tenant_id, subscription_id


def _group_costs(facts, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    totals: dict[tuple, float] = defaultdict(float)
    for fact in facts:
        group = tuple(str(getattr(fact, key) or "Unassigned") for key in keys)
        totals[(*group, fact.currency)] += fact.cost_amount
    rows = []
    for key, amount in sorted(totals.items(), key=lambda row: row[1], reverse=True):
        row = {name: key[index] for index, name in enumerate(keys)}
        row.update(currency=key[-1], costAmount=round(amount, 6))
        rows.append(row)
    return rows


def _latest_costs(app: FastAPI, tenant_id: str, subscription_id: str):
    facts = app.state.storage.cost_facts.list_latest(tenant_id, subscription_id)
    settings: Settings = app.state.settings
    if (
        facts
        or tenant_id != settings.effective_tenant_id
        or subscription_id != settings.effective_subscription_id
    ):
        return facts
    frame = DashboardDataLoader(settings).load().cost_facts
    return [
        SimpleNamespace(**row)
        for row in frame.to_dict(orient="records")
    ]


def _latest_resources(app: FastAPI, tenant_id: str, subscription_id: str):
    facts = app.state.storage.resources.list_latest(tenant_id, subscription_id)
    settings: Settings = app.state.settings
    if (
        facts
        or tenant_id != settings.effective_tenant_id
        or subscription_id != settings.effective_subscription_id
    ):
        return facts
    frame = DashboardDataLoader(settings).load().resources
    return [
        SimpleNamespace(**row)
        for row in frame.to_dict(orient="records")
    ]


def _serialize(item) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return _dump(item)
    def camel(name: str) -> str:
        head, *tail = name.split("_")
        return head + "".join(part.capitalize() for part in tail)

    return {
        camel(key): (
            None
            if isinstance(value, float) and math.isnan(value)
            else value
        )
        for key, value in vars(item).items()
    }


def _cleanup_expired_sessions(storage) -> None:
    sessions = getattr(storage, "sessions", None)
    container = getattr(sessions, "container", None)
    if not sessions or not container:
        return
    now = datetime.now(timezone.utc)
    try:
        rows = list(
            container.query_items(
                query="SELECT c.id, c.expiresAt FROM c",
                enable_cross_partition_query=True,
            )
        )
    except Exception:
        return
    for row in rows:
        expires_at = str(row.get("expiresAt") or "")
        if not expires_at:
            continue
        try:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed <= now:
            try:
                sessions.delete(str(row.get("id")))
            except Exception:
                continue


def create_app(
    settings: Settings | None = None,
    *,
    storage=None,
    inventory_factory=ResourceGraphInventoryService,
    advisor_factory=FinOpsAdvisor,
    auth_factory=EntraAuthService,
) -> FastAPI:
    settings = settings or get_settings()
    storage = storage or create_storage_provider(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="FinsOpsIQ API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.storage = storage
    app.state.metrics = ApiMetrics()
    app.state.inventory_factory = inventory_factory
    app.state.advisor_factory = advisor_factory
    app.state.auth_factory = auth_factory
    app.state.credential_factory = CustomerTenantCredentialFactory(
        settings,
        storage,
    )
    app.state.auth_flows = {}
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "storageProvider": settings.storage_provider}

    @app.get("/api/metrics")
    def metrics(request: Request):
        get_identity(request)
        return request.app.state.metrics.snapshot()

    @app.get("/api/auth/login")
    def login(request: Request):
        if not settings.entra_auth_enabled:
            return RedirectResponse(f"{settings.frontend_url}/dashboard")
        service = request.app.state.auth_factory(settings)
        flow = service.begin_login()
        state = str(flow.get("state", ""))
        if not state:
            raise HTTPException(500, "Microsoft login did not return state")
        request.app.state.auth_flows[state] = flow
        return RedirectResponse(str(flow["auth_uri"]))

    @app.get("/api/auth/callback")
    def auth_callback(request: Request):
        _cleanup_expired_sessions(storage)
        params = dict(request.query_params)
        flow = request.app.state.auth_flows.pop(str(params.get("state", "")), None)
        if not flow:
            raise HTTPException(400, "Login flow expired or state is invalid")
        session = request.app.state.auth_factory(settings).complete_login(flow, params)
        TenantOnboardingService(settings, storage=storage).register_authenticated_user(
            session
        )
        roles = next(
            (
                user.roles
                for user in storage.tenant_users.list(session.profile.tenant_id)
                if user.user_id == session.profile.user_id
            ),
            ["tenant_user"],
        )
        token = SessionTokenService(settings).issue(
            {
                "tid": session.profile.tenant_id,
                "oid": session.profile.user_id,
                "email": session.profile.email,
                "name": session.profile.display_name,
                "roles": roles,
            }
        )
        session_id = str(uuid.uuid4())
        storage.sessions.upsert(
            ServerSession(
                sessionId=session_id,
                tenantId=session.profile.tenant_id,
                userId=session.profile.user_id,
                authSession=session.model_dump(by_alias=True, mode="json"),
                expiresAt=session.expires_at,
            )
        )
        response = RedirectResponse(f"{settings.frontend_url}/dashboard")
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=settings.api_session_cookie_secure,
            samesite="lax",
            max_age=8 * 60 * 60,
        )
        response.set_cookie(
            "finops_sid",
            session_id,
            httponly=True,
            secure=settings.api_session_cookie_secure,
            samesite="lax",
            max_age=8 * 60 * 60,
        )
        return response

    @app.get("/api/auth/logout")
    @app.post("/api/auth/logout")
    def logout(request: Request):
        session_id = request.cookies.get("finops_sid", "")
        if session_id:
            storage.sessions.delete(session_id)
        url = (
            request.app.state.auth_factory(settings).logout_url()
            if settings.entra_auth_enabled
            else settings.frontend_url
        )
        response = RedirectResponse(url, status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie("finops_sid")
        return response

    @app.get("/api/auth/me")
    def me(request: Request):
        _cleanup_expired_sessions(storage)
        identity = get_identity(request)
        return {
            "tenant_id": identity.tenant_id,
            "user_id": identity.user_id,
            "display_name": identity.display_name,
            "tenantId": identity.tenant_id,
            "userId": identity.user_id,
            "email": identity.email,
            "displayName": identity.display_name,
            "roles": identity.roles,
        }

    @app.get("/api/tenants")
    def tenants(request: Request):
        identity = get_identity(request)
        if identity.platform_admin:
            return [_dump(item) for item in storage.tenants.list()]
        tenant = storage.tenants.get(identity.tenant_id)
        return [_dump(tenant)] if tenant else [
            {
                "tenantId": identity.tenant_id,
                "displayName": identity.tenant_id,
                "status": "legacy",
            }
        ]

    @app.get("/api/tenants/{tenant_id}")
    def tenant(tenant_id: str, request: Request):
        identity = get_identity(request)
        if tenant_id != identity.tenant_id and not identity.platform_admin:
            raise HTTPException(403, "Tenant access denied")
        item = storage.tenants.get(tenant_id)
        if not item:
            raise HTTPException(404, "Tenant not found")
        return _dump(item)

    @app.get("/api/subscriptions")
    def subscriptions(request: Request):
        identity = get_identity(request)
        tenant_id = tenant_scope(request, identity)
        return [_dump(item) for item in storage.subscriptions.list(tenant_id)]

    @app.get("/api/subscriptions/{subscription_id}")
    def subscription(subscription_id: str, request: Request):
        identity = get_identity(request)
        tenant_id = tenant_scope(request, identity)
        item = next(
            (
                item
                for item in storage.subscriptions.list(tenant_id)
                if item.subscription_id == subscription_id
            ),
            None,
        )
        if not item:
            raise HTTPException(404, "Subscription not found")
        return _dump(item)

    @app.get("/api/costs/summary")
    def cost_summary(request: Request):
        _, tenant_id, subscription_id = _scopes(request)
        facts = _latest_costs(request.app, tenant_id, subscription_id)
        totals: dict[str, float] = defaultdict(float)
        for fact in facts:
            totals[fact.currency] += fact.cost_amount
        return {
            "tenantId": tenant_id,
            "subscriptionId": subscription_id,
            "totals": [
                {"currency": currency, "amount": round(amount, 6)}
                for currency, amount in sorted(totals.items())
            ],
            "recordCount": len(facts),
            "sourceSystem": "Azure Cost Management",
        }

    @app.get("/api/costs/trends")
    def cost_trends(request: Request, granularity: str = Query("daily")):
        _, tenant_id, subscription_id = _scopes(request)
        facts = _latest_costs(request.app, tenant_id, subscription_id)
        key = "date"
        if granularity == "monthly":
            totals: dict[tuple[str, str], float] = defaultdict(float)
            for fact in facts:
                totals[(fact.date.strftime("%Y-%m"), fact.currency)] += fact.cost_amount
            return [
                {"period": period, "currency": currency, "costAmount": amount}
                for (period, currency), amount in sorted(totals.items())
            ]
        return _group_costs(facts, (key,))

    @app.get("/api/costs/services")
    def cost_services(request: Request):
        _, tenant_id, subscription_id = _scopes(request)
        return _group_costs(
            _latest_costs(request.app, tenant_id, subscription_id),
            ("service_name",),
        )

    @app.get("/api/costs/resource-groups")
    def cost_resource_groups(request: Request):
        _, tenant_id, subscription_id = _scopes(request)
        return _group_costs(
            _latest_costs(request.app, tenant_id, subscription_id),
            ("resource_group",),
        )

    @app.get("/api/resources")
    def resources(request: Request, search: str = ""):
        _, tenant_id, subscription_id = _scopes(request)
        items = _latest_resources(request.app, tenant_id, subscription_id)
        needle = search.lower().strip()
        if needle:
            items = [
                item
                for item in items
                if needle in item.resource_name.lower()
                or needle in item.resource_type.lower()
                or needle in item.resource_group.lower()
            ]
        return [_serialize(item) for item in items]

    @app.get("/api/resources/{resource_id:path}")
    def resource(resource_id: str, request: Request):
        _, tenant_id, subscription_id = _scopes(request)
        normalized = resource_id.strip().rstrip("/").lower()
        item = next(
            (
                item
                for item in _latest_resources(
                    request.app, tenant_id, subscription_id
                )
                if item.resource_id == normalized
            ),
            None,
        )
        if not item:
            raise HTTPException(404, "Resource not found")
        return _serialize(item)

    @app.get("/api/recommendations")
    def recommendations(request: Request):
        _, tenant_id, subscription_id = _scopes(request)
        return [
            _dump(item)
            for item in storage.recommendations.list_latest(
                tenant_id, subscription_id
            )
        ]

    @app.post("/api/chat")
    def chat(request: Request, body: dict[str, Any] = Body(...)):
        _, tenant_id, subscription_id = _scopes(request)
        question = str(body.get("message", "")).strip()
        if not question:
            raise HTTPException(422, "message is required")
        advisor_kwargs = {
            "tenant_id": tenant_id,
            "subscription_ids": [subscription_id],
        }
        if request.app.state.advisor_factory is FinOpsAdvisor:
            advisor_kwargs["credential"] = (
                request.app.state.credential_factory.for_subscription(
                    tenant_id,
                    subscription_id,
                )
            )
        advisor = request.app.state.advisor_factory(settings, **advisor_kwargs)
        return {
            "answer": advisor.ask(question, str(body.get("history", ""))),
            "tenantId": tenant_id,
            "subscriptionId": subscription_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def inventory(request: Request, kind: str):
        _, tenant_id, subscription_id = _scopes(request)
        inventory_kwargs = {
            "tenant_id": tenant_id,
            "subscription_ids": [subscription_id],
        }
        if request.app.state.inventory_factory is ResourceGraphInventoryService:
            inventory_kwargs["credential"] = (
                request.app.state.credential_factory.for_subscription(
                    tenant_id,
                    subscription_id,
                )
            )
        return request.app.state.inventory_factory(
            settings,
            **inventory_kwargs,
        ).query(INVENTORY_QUESTIONS[kind])

    def inventory_endpoint(kind: str) -> Callable:
        def endpoint(request: Request):
            return inventory(request, kind)

        endpoint.__name__ = f"inventory_{kind.replace('-', '_')}"
        return endpoint

    for kind in INVENTORY_QUESTIONS:
        app.add_api_route(
            f"/api/inventory/{kind}",
            inventory_endpoint(kind),
            methods=["GET"],
            name=f"inventory_{kind}",
        )

    return app


app = create_app()
