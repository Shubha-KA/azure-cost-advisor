"""AI service application logic."""

from __future__ import annotations

from datetime import datetime, timezone

from src.ai.advisor import FinOpsAdvisor
from src.ai.inventory import ResourceGraphInventoryService
from src.ai.service import AIService
from src.auth.customer_credentials import CustomerTenantCredentialFactory
from src.events.contracts import EventType, PlatformEvent
from src.observability import measure
from src.service_contracts.internal import ServiceScope


class AIApplicationService:
    def __init__(self, app) -> None:
        self.app = app
        if not hasattr(app.state, "credential_factory"):
            app.state.credential_factory = CustomerTenantCredentialFactory(
                app.state.settings,
                app.state.storage,
            )

    def _credential(self, scope: ServiceScope):
        return self.app.state.credential_factory.for_subscription(
            scope.tenant_id,
            scope.subscription_id,
        )

    def process_event(self, event: PlatformEvent):
        if event.event_type != EventType.PROCESSING_COMPLETED:
            return {"status": "ignored"}
        with measure("search_index", tenantId=event.tenant_id):
            count = AIService(
                self.app.state.settings,
                storage=self.app.state.storage,
            ).index_subscription(event.tenant_id, event.subscription_id)
        return {"status": "indexed", "documents": count}

    def chat(self, scope: ServiceScope, body: dict, correlation_id: str):
        question = str(body["message"])
        with measure(
            "ai_chat",
            tenantId=scope.tenant_id,
            subscriptionId=scope.subscription_id,
        ):
            answer = FinOpsAdvisor(
                self.app.state.settings,
                tenant_id=scope.tenant_id,
                subscription_ids=[scope.subscription_id],
                credential=self._credential(scope),
            ).ask(question, str(body.get("history", "")))
        self.app.state.events.publish(
            PlatformEvent(
                eventType=EventType.AI_CHAT_EXECUTED,
                tenantId=scope.tenant_id,
                subscriptionId=scope.subscription_id,
                correlationId=correlation_id,
                producer="ai-service",
                payload={"questionLength": len(question)},
            )
        )
        return {
            "answer": answer,
            "tenantId": scope.tenant_id,
            "subscriptionId": scope.subscription_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def generate_recommendations(self, scope: ServiceScope, correlation_id: str):
        result = FinOpsAdvisor(
            self.app.state.settings,
            tenant_id=scope.tenant_id,
            subscription_ids=[scope.subscription_id],
        ).generate_recommendations()
        self.app.state.events.publish(
            PlatformEvent(
                eventType=EventType.RECOMMENDATION_GENERATED,
                tenantId=scope.tenant_id,
                subscriptionId=scope.subscription_id,
                correlationId=correlation_id,
                producer="ai-service",
                payload={"source": result.get("source", "")},
            )
        )
        return result

    def inventory(self, scope: ServiceScope, kind: str):
        questions = {
            "resource-groups": "What resource groups do I have?",
            "vms": "What VMs exist?",
            "aks": "What AKS clusters exist?",
            "storage": "Show storage accounts",
            "keyvaults": "Show Key Vaults",
        }
        return ResourceGraphInventoryService(
            self.app.state.settings,
            tenant_id=scope.tenant_id,
            subscription_ids=[scope.subscription_id],
            credential=self._credential(scope),
        ).query(questions[kind])
