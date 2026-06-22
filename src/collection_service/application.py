"""Collection service application logic."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import jwt

from src.auth.customer_credentials import CustomerTenantCredentialFactory
from src.collector.run import run_all as default_run_all
from src.domain.context import OperationContext
from src.domain.models import CollectionRun
from src.events.contracts import EventType, PlatformEvent
from src.observability import measure

logger = logging.getLogger(__name__)


class CollectionApplicationService:
    def __init__(
        self,
        app,
        *,
        run_all_func: Callable[..., Any] = default_run_all,
    ) -> None:
        self.app = app
        self.run_all_func = run_all_func
        if not hasattr(app.state, "credential_factory"):
            app.state.credential_factory = CustomerTenantCredentialFactory(
                app.state.settings,
                app.state.storage,
            )

    def collect_subscription(self, body: dict):
        context = OperationContext.create(
            str(body["tenantId"]), str(body["subscriptionId"])
        )
        publisher = self.app.state.events
        publisher.publish(
            PlatformEvent(
                eventType=EventType.COLLECTION_STARTED,
                **context.document_fields(),
                producer="collection-service",
            )
        )
        try:
            with measure(
                "collection",
                tenantId=context.tenant_id,
                subscriptionId=context.subscription_id,
            ):
                credential = self.app.state.credential_factory.for_subscription(
                    context.tenant_id,
                    context.subscription_id,
                )
                report = self.run_all_func(
                    settings=self.app.state.settings,
                    context=context,
                    storage=self.app.state.storage,
                    credential=credential,
                    continue_on_error=bool(body.get("continueOnError", True)),
                )
        except Exception as exc:
            completed_at = datetime.now(timezone.utc).isoformat()
            self.app.state.storage.processing_metadata.upsert(
                context.tenant_id,
                {
                    **CollectionRun(
                        tenantId=context.tenant_id,
                        subscriptionId=context.subscription_id,
                        collectionRunId=context.collection_run_id,
                        processingRunId=context.processing_run_id,
                        correlationId=context.correlation_id,
                        status="failed",
                        startedAt=completed_at,
                        completedAt=completed_at,
                        errors=[str(exc)],
                    ).model_dump(by_alias=True, mode="json"),
                    "metadataType": "collectionRun",
                    "startTime": completed_at,
                    "endTime": completed_at,
                },
            )
            publisher.publish(
                PlatformEvent(
                    eventType=EventType.HEALTH_CHECK_FAILED,
                    **context.document_fields(),
                    producer="collection-service",
                    payload={"operation": "collection", "error": str(exc)},
                )
            )
            raise
        completed_event = PlatformEvent(
            eventType=EventType.COLLECTION_COMPLETED,
            **context.document_fields(),
            producer="collection-service",
            payload={
                "status": "partial" if report.errors else "completed",
                "recordsCollected": sum(item.record_count for item in report.results),
                "errors": report.errors,
            },
        )
        publisher.publish(completed_event)
        if not report.errors:
            self._forward_event_for_local_compose(completed_event)
        return asdict(report)

    def _forward_event_for_local_compose(self, event: PlatformEvent) -> None:
        settings = self.app.state.settings
        if settings.event_provider.lower() == "service_bus":
            return
        if not settings.processing_service_url:
            return
        token = jwt.encode(
            {
                "iss": "azure-cost-advisor",
                "aud": settings.internal_api_audience,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
            },
            settings.api_session_secret,
            algorithm="HS256",
        )
        url = f"{settings.processing_service_url}/internal/events"
        try:
            response = httpx.post(
                url,
                json=event.model_dump(by_alias=True, mode="json"),
                headers={"Authorization": f"Bearer {token}"},
                timeout=300,
            )
            if response.status_code >= 400:
                logger.error(
                    "processing_event_forward_failed url=%s status_code=%s response=%s",
                    url,
                    response.status_code,
                    response.text[:1000],
                )
            else:
                logger.info(
                    "processing_event_forward_success url=%s status_code=%s",
                    url,
                    response.status_code,
                )
        except httpx.RequestError as exc:
            logger.error(
                "processing_event_forward_request_error url=%s exception=%s message=%s",
                url,
                type(exc).__name__,
                str(exc),
            )

    def run_scheduled_cycle(self) -> dict:
        attempted = 0
        failed = 0
        for tenant in self.app.state.storage.tenants.list():
            subscriptions = self.app.state.storage.subscriptions.list(
                tenant.tenant_id
            )
            for subscription in subscriptions:
                if not (
                    subscription.selected
                    and subscription.onboarding_status == "validated"
                    and subscription.status.lower() not in {"disabled", "deleted"}
                ):
                    continue
                attempted += 1
                try:
                    self.collect_subscription(
                        {
                            "tenantId": tenant.tenant_id,
                            "subscriptionId": subscription.subscription_id,
                            "continueOnError": True,
                        }
                    )
                except Exception as exc:
                    failed += 1
                    logger.exception(
                        "scheduled_collection_failed tenantId=%s subscriptionId=%s",
                        tenant.tenant_id,
                        subscription.subscription_id,
                    )
                    self.app.state.events.publish(
                        PlatformEvent(
                            eventType=EventType.HEALTH_CHECK_FAILED,
                            tenantId=tenant.tenant_id,
                            subscriptionId=subscription.subscription_id,
                            correlationId=f"scheduled-{int(time.time())}",
                            producer="collection-service",
                            payload={
                                "operation": "scheduled_collection",
                                "error": str(exc),
                            },
                        )
                    )
        return {"subscriptionsAttempted": attempted, "failures": failed}


def scheduler_loop(service: CollectionApplicationService, stop: threading.Event) -> None:
    interval = service.app.state.settings.collection_interval_minutes * 60
    while not stop.is_set():
        service.run_scheduled_cycle()
        stop.wait(interval)
