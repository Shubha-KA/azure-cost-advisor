"""Notification service application logic."""

from __future__ import annotations

import logging

from src.events.contracts import EventType, PlatformEvent

logger = logging.getLogger(__name__)


class NotificationApplicationService:
    def __init__(self, app) -> None:
        self.app = app

    def process_event(self, event: PlatformEvent):
        if event.event_type not in {
            EventType.RECOMMENDATION_GENERATED,
            EventType.HEALTH_CHECK_FAILED,
            EventType.PROCESSING_COMPLETED,
        }:
            return {"status": "ignored"}
        settings = self.app.state.settings
        recipient = str(event.payload.get("recipient", ""))
        if recipient and settings.email_connection_string and settings.email_sender:
            from azure.communication.email import EmailClient

            client = EmailClient.from_connection_string(settings.email_connection_string)
            poller = client.begin_send(
                {
                    "senderAddress": settings.email_sender,
                    "recipients": {"to": [{"address": recipient}]},
                    "content": {
                        "subject": f"FinsOpsIQ: {event.event_type.value}",
                        "plainText": str(event.payload),
                    },
                }
            )
            result = poller.result()
            return {"status": "sent", "messageId": result.get("id", "")}
        logger.info(
            "notification_logged event=%s tenantId=%s payload=%s",
            event.event_type,
            event.tenant_id,
            event.payload,
        )
        return {"status": "logged", "reason": "email_not_configured"}

    def scheduled_report(self, body: dict, correlation_id: str):
        event = PlatformEvent(
            eventType=EventType.PROCESSING_COMPLETED,
            tenantId=str(body["tenantId"]),
            subscriptionId=str(body["subscriptionId"]),
            correlationId=correlation_id,
            producer="notification-service",
            payload={
                "recipient": body.get("recipient", ""),
                "reportType": body.get("reportType", "monthly-finops"),
            },
        )
        return self.process_event(event)
