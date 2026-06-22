"""Processing service HTTP entrypoint."""

from __future__ import annotations

from fastapi import Body, Query, Request

from src.events.bus import create_event_publisher, start_subscription_worker
from src.events.contracts import PlatformEvent
from src.microservices.common import require_internal, service_app
from src.processing_service.application import ProcessingApplicationService
from src.processor.run import run_processing
from src.service_contracts.internal import ServiceScope

app = service_app("processing-service")
app.state.events = create_event_publisher(app.state.settings)
app.state.application = ProcessingApplicationService(
    app, run_processing_func=run_processing
)


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
    app.state.worker = start_subscription_worker(
        app, "processing-service", process_event
    )


def _scope(request: Request) -> ServiceScope:
    return ServiceScope.from_headers(request.headers)


@app.get("/internal/costs/summary")
def costs(request: Request):
    require_internal(request)
    return request.app.state.application.cost_summary(_scope(request))


@app.get("/internal/costs/trends")
def cost_trends(request: Request, granularity: str = Query("daily")):
    require_internal(request)
    return request.app.state.application.cost_trends(
        _scope(request), granularity=granularity
    )


@app.get("/internal/costs/services")
def cost_services(request: Request):
    require_internal(request)
    service = request.app.state.application
    return service.group_costs(service.cost_facts(_scope(request)), "service_name")


@app.get("/internal/costs/resource-groups")
def cost_resource_groups(request: Request):
    require_internal(request)
    service = request.app.state.application
    return service.group_costs(service.cost_facts(_scope(request)), "resource_group")


@app.get("/internal/resources")
def resources(request: Request):
    require_internal(request)
    return request.app.state.application.resources(_scope(request))


@app.get("/internal/resources/{resource_id:path}")
def resource(resource_id: str, request: Request):
    require_internal(request)
    return request.app.state.application.resource(_scope(request), resource_id)


@app.get("/internal/recommendations")
def recommendations(request: Request):
    require_internal(request)
    return request.app.state.application.recommendations(_scope(request))
