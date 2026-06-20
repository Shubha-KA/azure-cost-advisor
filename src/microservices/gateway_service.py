"""Public API gateway HTTP entrypoint."""

from __future__ import annotations

import httpx
from fastapi import Request

import src.gateway_service.application as gateway_application
from src.gateway_service.application import GatewayApplicationService
from src.microservices.common import service_app

app = service_app("api-gateway")
app.state.application = GatewayApplicationService(app)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("//api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    gateway_application.httpx = httpx
    return await request.app.state.application.proxy(path, request)
