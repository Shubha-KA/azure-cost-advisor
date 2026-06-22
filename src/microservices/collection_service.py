"""Collection service HTTP entrypoint."""

from __future__ import annotations

import threading

from fastapi import Body, Request

from src.collection_service.application import (
    CollectionApplicationService,
    scheduler_loop,
)
from src.collector.run import run_all
from src.events.bus import create_event_publisher
from src.microservices.common import require_internal, service_app

app = service_app("collection-service")
app.state.events = create_event_publisher(app.state.settings)
app.state.application = CollectionApplicationService(app, run_all_func=run_all)


def _application(request_app):
    if not hasattr(request_app.state, "application"):
        request_app.state.application = CollectionApplicationService(
            request_app, run_all_func=run_all
        )
    return request_app.state.application


def _collect_subscription(request_app, body: dict):
    service = _application(request_app)
    service.run_all_func = run_all
    return service.collect_subscription(body)


@app.post("/internal/collections")
def collect(request: Request, body: dict = Body(...)):
    require_internal(request)
    service = _application(request.app)
    service.run_all_func = run_all
    return service.collect_subscription(body)


def run_scheduled_cycle(request_app=app) -> dict:
    return _application(request_app).run_scheduled_cycle()


@app.on_event("startup")
def start_scheduler():
    if not app.state.settings.collection_scheduler_enabled:
        return
    app.state.scheduler_stop = threading.Event()
    app.state.scheduler_thread = threading.Thread(
        target=scheduler_loop,
        args=(app.state.application, app.state.scheduler_stop),
        name="collection-scheduler",
        daemon=True,
    )
    app.state.scheduler_thread.start()


@app.on_event("shutdown")
def stop_scheduler():
    stop = getattr(app.state, "scheduler_stop", None)
    if stop is not None:
        stop.set()
