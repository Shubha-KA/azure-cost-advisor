"""Auth service HTTP entrypoint."""

from __future__ import annotations

from fastapi import Body, Request

from src.auth_service.application import AuthApplicationService
from src.events.bus import create_event_publisher
from src.microservices.common import service_app

app = service_app("auth-service")
app.state.events = create_event_publisher(app.state.settings)
app.state.application = AuthApplicationService(app)

import logging
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    logger.info("auth_service_startup collection_service_url=%s", app.state.settings.collection_service_url)


@app.get("/api/auth/login")
def login():
    return app.state.application.login()


@app.get("/api/auth/callback")
def callback(request: Request):
    return app.state.application.callback(request)


@app.get("/api/auth/logout")
def logout(request: Request):
    return app.state.application.logout_request(request)


@app.get("/api/auth/me")
def me(request: Request):
    return app.state.application.me(request)


@app.get("/api/tenants")
def tenants(request: Request):
    return app.state.application.tenants(request)


@app.get("/api/subscriptions")
def subscriptions(request: Request):
    return app.state.application.subscriptions(request)


@app.get("/api/tenant-health")
def tenant_health(request: Request):
    return app.state.application.tenant_health(request)


@app.post("/api/tenants/{tenant_id}/offboarding")
def offboard(tenant_id: str, request: Request, body: dict = Body(default={})):
    return app.state.application.offboard(tenant_id, request, body)


@app.get("/api/onboarding/status")
def onboarding_status(request: Request):
    return app.state.application.onboarding_status(request)


@app.get("/api/onboarding/subscriptions/discover")
def discover_subscriptions(request: Request):
    return app.state.application.discover_subscriptions(request)


@app.post("/api/onboarding/subscriptions/select")
async def select_subscriptions(request: Request, body: dict = Body(...)):
    return await app.state.application.select_subscriptions(request, body)


@app.post("/api/onboarding/collection/retry")
async def retry_collection(request: Request):
    return await app.state.application.retry_collection(request)
