"""Auth service HTTP entrypoint."""

from __future__ import annotations

from fastapi import Body, Request

from src.auth_service.application import AuthApplicationService
from src.events.bus import create_event_publisher
from src.microservices.common import service_app

app = service_app("auth-service")
app.state.events = create_event_publisher(app.state.settings)
app.state.application = AuthApplicationService(app)


@app.get("/api/auth/login")
def login():
    return app.state.application.login()


@app.get("/api/auth/callback")
def callback(request: Request):
    return app.state.application.callback(request)


@app.post("/api/auth/logout")
def logout():
    return app.state.application.logout()


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
