"""Processing service application logic and read model endpoints."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date

from fastapi import HTTPException

from src.domain.context import OperationContext
from src.events.contracts import EventType, PlatformEvent
from src.observability import measure
from src.processor.run import run_processing as default_run_processing
from src.service_contracts.internal import ServiceScope


class ProcessingApplicationService:
    def __init__(self, app, *, run_processing_func=default_run_processing) -> None:
        self.app = app
        self.run_processing_func = run_processing_func

    def context_from_event(self, event: PlatformEvent) -> OperationContext:
        return OperationContext(
            tenantId=event.tenant_id,
            subscriptionId=event.subscription_id,
            collectionRunId=event.collection_run_id,
            processingRunId=event.processing_run_id,
            correlationId=event.correlation_id,
            schemaVersion=event.schema_version,
        )

    def process_event(self, event: PlatformEvent):
        if event.event_type != EventType.COLLECTION_COMPLETED:
            return {"status": "ignored", "eventType": event.event_type}
        context = self.context_from_event(event)
        self.app.state.events.publish(
            PlatformEvent(
                eventType=EventType.PROCESSING_STARTED,
                **context.document_fields(),
                producer="processing-service",
            )
        )
        with measure(
            "processing",
            tenantId=context.tenant_id,
            subscriptionId=context.subscription_id,
        ):
            _, report = self.run_processing_func(
                settings=self.app.state.settings,
                context=context,
                storage=self.app.state.storage,
            )
        self.app.state.events.publish(
            PlatformEvent(
                eventType=EventType.PROCESSING_COMPLETED,
                **context.document_fields(),
                producer="processing-service",
                payload={
                    "costFacts": report.cost_fact_count,
                    "resourceFacts": report.resource_fact_count,
                    "reconciliationStatus": report.reconciliation_status,
                },
            )
        )
        return asdict(report)

    def cost_summary(self, scope: ServiceScope):
        facts = self.app.state.storage.cost_facts.list_latest(
            scope.tenant_id, scope.subscription_id
        )
        totals = defaultdict(float)
        for fact in facts:
            totals[fact.currency] += fact.cost_amount
        return {
            "tenantId": scope.tenant_id,
            "subscriptionId": scope.subscription_id,
            "totals": [
                {"currency": key, "amount": value}
                for key, value in sorted(totals.items())
            ],
            "recordCount": len(facts),
        }

    def cost_facts(self, scope: ServiceScope):
        return self.app.state.storage.cost_facts.list_latest(
            scope.tenant_id, scope.subscription_id
        )

    def group_costs(self, facts, attribute: str):
        totals = defaultdict(float)
        for fact in facts:
            value = getattr(fact, attribute)
            if isinstance(value, date):
                value = value.isoformat()
            totals[(str(value or "Unassigned"), fact.currency)] += fact.cost_amount
        return [
            {
                attribute: key,
                "currency": currency,
                "costAmount": round(amount, 6),
            }
            for (key, currency), amount in sorted(totals.items())
        ]

    def cost_trends(self, scope: ServiceScope, granularity: str = "daily"):
        facts = self.cost_facts(scope)
        if granularity == "monthly":
            totals = defaultdict(float)
            for fact in facts:
                totals[(fact.date.strftime("%Y-%m"), fact.currency)] += fact.cost_amount
            return [
                {
                    "period": period,
                    "currency": currency,
                    "costAmount": round(amount, 6),
                }
                for (period, currency), amount in sorted(totals.items())
            ]
        return self.group_costs(facts, "date")

    def resources(self, scope: ServiceScope):
        return [
            item.model_dump(by_alias=True, mode="json")
            for item in self.app.state.storage.resources.list_latest(
                scope.tenant_id, scope.subscription_id
            )
        ]

    def resource(self, scope: ServiceScope, resource_id: str):
        normalized = resource_id.strip().rstrip("/").lower()
        item = next(
            (
                item
                for item in self.app.state.storage.resources.list_latest(
                    scope.tenant_id, scope.subscription_id
                )
                if item.resource_id == normalized
            ),
            None,
        )
        if item is None:
            raise HTTPException(404, "Resource not found")
        return item.model_dump(by_alias=True, mode="json")

    def recommendations(self, scope: ServiceScope):
        return [
            item.model_dump(by_alias=True, mode="json")
            for item in self.app.state.storage.recommendations.list_latest(
                scope.tenant_id, scope.subscription_id
            )
        ]
