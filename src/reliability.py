"""Retry, circuit-breaker, and graceful-degradation primitives."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_seconds: float = 30.0

    def __post_init__(self) -> None:
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def call(self, operation, *args, **kwargs):
        with self._lock:
            if (
                self._failures >= self.failure_threshold
                and time.monotonic() - self._opened_at < self.recovery_seconds
            ):
                raise CircuitOpenError("Circuit breaker is open")
        try:
            result = operation(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = time.monotonic()
            raise
        with self._lock:
            self._failures = 0
        return result

    async def call_async(self, operation, *args, **kwargs):
        with self._lock:
            if (
                self._failures >= self.failure_threshold
                and time.monotonic() - self._opened_at < self.recovery_seconds
            ):
                raise CircuitOpenError("Circuit breaker is open")
        try:
            result = await operation(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = time.monotonic()
            raise
        with self._lock:
            self._failures = 0
        return result
