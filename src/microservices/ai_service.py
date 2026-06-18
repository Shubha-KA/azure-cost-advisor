"""AI service HTTP entrypoint."""

from __future__ import annotations

from fastapi import Body, Request

from src.ai_service.application import AIApplicationService
from src.events.bus import create_event_publisher, start_subscription_worker
from src.events.contracts import PlatformEvent
from src.microservices.common import require_internal, service_app
from src.service_contracts.internal import ServiceScope

app = service_app("ai-service")
app.state.events = create_event_publisher(app.state.settings)
app.state.application = AIApplicationService(app)


def _scope(request: Request) -> ServiceScope:
    return ServiceScope.from_headers(request.headers)


def process_event(event: PlatformEvent, request_app=app):
    return request_app.state.application.process_event(event)


@app.post("/internal/events")
def event_handler(request: Request, body: dict = Body(...)):
    require_internal(request)
    return request.app.state.application.process_event(
        PlatformEvent.model_validate(body)
    )


@app.on_event("startup")
def start_worker():
    app.state.worker = start_subscription_worker(app, "ai-service", process_event)


@app.post("/internal/chat")
def chat(request: Request, body: dict = Body(...)):
    require_internal(request)
    return request.app.state.application.chat(
        _scope(request), body, request.state.correlation_id
    )


@app.post("/internal/recommendations/generate")
def generate_recommendations(request: Request):
    require_internal(request)
    return request.app.state.application.generate_recommendations(
        _scope(request), request.state.correlation_id
    )


@app.get("/internal/inventory/{kind}")
def inventory(kind: str, request: Request):
    require_internal(request)
    return request.app.state.application.inventory(_scope(request), kind)
