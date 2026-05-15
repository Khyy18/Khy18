"""Circuit breaker pattern and graceful degradation for external services."""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


class CircuitState(str, enum.Enum):
    """States for a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted on an open circuit."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        super().__init__(f"Circuit breaker is open for service: {service_name}")


class CircuitBreaker:
    """Circuit breaker for protecting external service calls.

    Tracks consecutive failures and opens the circuit when the threshold
    is exceeded. After recovery_timeout seconds, transitions to HALF_OPEN
    to allow a single test call.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._service_name = service_name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state, evaluating timeout transitions."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def is_available(self) -> bool:
        """Return True if the circuit allows calls (CLOSED or HALF_OPEN)."""
        return self.state != CircuitState.OPEN

    @property
    def failure_count(self) -> int:
        """Return the current failure count."""
        return self._failure_count

    @property
    def last_failure_time(self) -> float | None:
        """Return the timestamp of the last recorded failure."""
        return self._last_failure_time

    @last_failure_time.setter
    def last_failure_time(self, value: float | None) -> None:
        """Set the last failure time (useful for testing)."""
        self._last_failure_time = value

    async def call(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Execute a coroutine with circuit breaker protection.

        If CLOSED: execute and track failures.
        If OPEN: check timeout, raise CircuitOpenError if not elapsed.
        If HALF_OPEN: try one call; success resets, failure reopens.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitOpenError(self._service_name)

        try:
            result = await coro
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        logger.debug("Circuit breaker '%s' recorded success, state=CLOSED", self._service_name)

    def record_failure(self) -> None:
        """Record a failed call. Opens circuit if threshold is reached."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' opened after %d failures",
                self._service_name,
                self._failure_count,
            )
        elif self._state == CircuitState.HALF_OPEN:
            # Failure in half-open state reopens the circuit
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' re-opened from HALF_OPEN after failure",
                self._service_name,
            )

    def reset(self) -> None:
        """Force-reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        logger.info("Circuit breaker '%s' manually reset to CLOSED", self._service_name)


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers by service name."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> CircuitBreaker:
        """Get an existing breaker or create a new one for the service."""
        if service_name not in self._breakers:
            self._breakers[service_name] = CircuitBreaker(
                service_name=service_name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return self._breakers[service_name]

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Return status of all registered circuit breakers."""
        result: dict[str, dict[str, Any]] = {}
        for name, breaker in self._breakers.items():
            result[name] = {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "is_available": breaker.is_available,
                "last_failure_time": breaker.last_failure_time,
            }
        return result


class GracefulDegradation:
    """Provides fallback modes when services are unavailable."""

    # Fallback rules for each known service
    _FALLBACK_RULES: dict[str, dict[str, str]] = {
        "redis": {
            "mode": "in_memory_cache",
            "description": "Using in-memory cache, rate limiting disabled",
        },
        "llm": {
            "mode": "template_only",
            "description": "Using cached/template responses",
        },
        "smtp": {
            "mode": "queue_retry",
            "description": "Messages queued for retry",
        },
        "linkedin": {
            "mode": "email_only",
            "description": "LinkedIn steps skipped, email-only mode",
        },
        "postgres": {
            "mode": "service_unavailable",
            "description": "Service unavailable, data queued in Redis",
        },
    }

    def __init__(self, registry: CircuitBreakerRegistry) -> None:
        self._registry = registry

    def get_fallback_mode(self, service_name: str) -> dict[str, str]:
        """Get the fallback mode for a service.

        Returns a dict with 'mode' and 'description' keys.
        If the service has no defined fallback, returns a generic response.
        """
        fallback = self._FALLBACK_RULES.get(service_name)
        if fallback is not None:
            return fallback
        return {
            "mode": "unknown",
            "description": f"No fallback defined for service: {service_name}",
        }
