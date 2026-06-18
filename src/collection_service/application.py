"""Collection service application logic."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from typing import Any, Callable

from src.auth.customer_credentials import CustomerTenantCredentialFactory
from src.collector.run import run_all as default_run_all
from src.domain.context import OperationContext
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
            publisher.publish(
                PlatformEvent(
                    eventType=EventType.HEALTH_CHECK_FAILED,
                    **context.document_fields(),
                    producer="collection-service",
                    payload={"operation": "collection", "error": str(exc)},
                )
            )
            raise
        publisher.publish(
            PlatformEvent(
                eventType=EventType.COLLECTION_COMPLETED,
                **context.document_fields(),
                producer="collection-service",
                payload={
                    "status": "partial" if report.errors else "completed",
                    "recordsCollected": sum(
                        item.record_count for item in report.results
                    ),
                    "errors": report.errors,
                },
            )
        )
        return asdict(report)

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
