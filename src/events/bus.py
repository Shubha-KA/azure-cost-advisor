"""Azure Service Bus transport with an in-memory test/development adapter."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from azure.identity import DefaultAzureCredential
from tenacity import retry, stop_after_attempt, wait_exponential

from src.events.contracts import PlatformEvent

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, event: PlatformEvent) -> None: ...


class InMemoryEventBus:
    def __init__(self) -> None:
        self.events: list[PlatformEvent] = []
        self.handlers: dict[str, list[Callable[[PlatformEvent], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[PlatformEvent], None]):
        self.handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: PlatformEvent) -> None:
        self.events.append(event)
        for handler in self.handlers.get(event.event_type.value, []):
            handler(event)


class AzureServiceBusPublisher:
    def __init__(self, settings, client=None) -> None:
        if not settings.service_bus_namespace:
            raise ValueError("SERVICE_BUS_NAMESPACE is required")
        if client is None:
            from azure.servicebus import ServiceBusClient

            client = ServiceBusClient(
                fully_qualified_namespace=settings.service_bus_namespace,
                credential=DefaultAzureCredential(),
            )
        self.client = client
        self.topic = settings.service_bus_topic

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    def publish(self, event: PlatformEvent) -> None:
        from azure.servicebus import ServiceBusMessage

        body = event.model_dump_json(by_alias=True)
        message = ServiceBusMessage(
            body,
            message_id=event.event_id,
            correlation_id=event.correlation_id,
            subject=event.event_type.value,
            application_properties={
                "tenantId": event.tenant_id,
                "subscriptionId": event.subscription_id,
                "schemaVersion": event.schema_version,
            },
        )
        with self.client.get_topic_sender(self.topic) as sender:
            sender.send_messages(message)


def create_event_publisher(settings) -> EventPublisher:
    if settings.event_provider.lower() == "service_bus":
        return AzureServiceBusPublisher(settings)
    return InMemoryEventBus()


def process_message(receiver, message, handler, *, max_attempts: int = 5) -> None:
    """Complete successful messages; abandon for retry; dead-letter poison data."""
    try:
        event = PlatformEvent.model_validate_json(str(message))
        handler(event)
        receiver.complete_message(message)
    except Exception as exc:
        delivery_count = int(getattr(message, "delivery_count", 1) or 1)
        logger.exception("event_processing_failed delivery_count=%d", delivery_count)
        if delivery_count >= max_attempts:
            receiver.dead_letter_message(
                message,
                reason="MaxDeliveryCountExceeded",
                error_description=str(exc)[:4096],
            )
        else:
            receiver.abandon_message(message)


def start_subscription_worker(
    app,
    subscription_name: str,
    handler: Callable[[PlatformEvent], None],
) -> threading.Thread | None:
    settings = app.state.settings
    if settings.event_provider.lower() != "service_bus":
        return None
    from azure.servicebus import ServiceBusClient

    def run() -> None:
        client = ServiceBusClient(
            fully_qualified_namespace=settings.service_bus_namespace,
            credential=DefaultAzureCredential(),
        )
        with client, client.get_subscription_receiver(
            topic_name=settings.service_bus_topic,
            subscription_name=subscription_name,
            max_wait_time=5,
        ) as receiver:
            while True:
                for message in receiver.receive_messages(
                    max_message_count=10, max_wait_time=5
                ):
                    process_message(receiver, message, handler)

    thread = threading.Thread(
        target=run,
        name=f"{subscription_name}-service-bus-worker",
        daemon=True,
    )
    thread.start()
    return thread
