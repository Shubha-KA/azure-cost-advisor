"""Notification service HTTP entrypoint."""

from __future__ import annotations

from fastapi import Body, Request

from src.events.bus import start_subscription_worker
from src.events.contracts import PlatformEvent
from src.microservices.common import require_internal, service_app
from src.notification_service.application import NotificationApplicationService

app = service_app("notification-service")
app.state.application = NotificationApplicationService(app)


def process_event(event: PlatformEvent, request_app=app):
    return request_app.state.application.process_event(event)


@app.post("/internal/events")
def notify(request: Request, body: dict = Body(...)):
    require_internal(request)
    return request.app.state.application.process_event(
        PlatformEvent.model_validate(body)
    )


@app.post("/internal/reports/scheduled")
def scheduled_report(request: Request, body: dict = Body(...)):
    require_internal(request)
    return request.app.state.application.scheduled_report(
        body, request.state.correlation_id
    )


@app.on_event("startup")
def start_worker():
    app.state.worker = start_subscription_worker(
        app, "notification-service", process_event
    )
