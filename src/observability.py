"""Application Insights bootstrap and consistent service telemetry."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("finops.telemetry")


def configure_observability(settings) -> None:
    if not settings.applicationinsights_connection_string:
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=settings.applicationinsights_connection_string,
            service_name=settings.service_name,
        )
    except Exception:
        logger.exception("application_insights_initialization_failed")


@contextmanager
def measure(operation: str, **dimensions):
    started = time.perf_counter()
    try:
        yield
    except Exception:
        logger.exception("operation_failed operation=%s dimensions=%s", operation, dimensions)
        raise
    finally:
        logger.info(
            "operation_duration operation=%s durationMs=%.2f dimensions=%s",
            operation,
            (time.perf_counter() - started) * 1000,
            dimensions,
        )
