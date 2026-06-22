"""Correlation, metrics, tracing, and audit middleware."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("finops.api.audit")


class ApiMetrics:
    def __init__(self) -> None:
        self.requests = 0
        self.errors = 0
        self.latency_ms = 0.0
        self.by_route: dict[str, int] = defaultdict(int)

    def snapshot(self) -> dict:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "averageLatencyMs": round(
                self.latency_ms / self.requests if self.requests else 0, 2
            ),
            "routes": dict(self.by_route),
        }


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            metrics: ApiMetrics = request.app.state.metrics
            metrics.requests += 1
            metrics.latency_ms += elapsed
            metrics.by_route[request.url.path] += 1
            status_code = response.status_code if response else 500
            if status_code >= 400:
                metrics.errors += 1
            logger.info(
                "api_request correlationId=%s method=%s path=%s status=%s latencyMs=%.2f",
                correlation_id,
                request.method,
                request.url.path,
                status_code,
                elapsed,
            )
            if response is not None:
                response.headers["X-Correlation-ID"] = correlation_id
