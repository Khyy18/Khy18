"""Circuit breaker pattern using tenacity for external API calls."""

import logging
import time
from functools import wraps
from typing import Any, Callable

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is in open state."""

    pass


class CircuitBreaker:
    """Simple circuit breaker that opens after consecutive failures."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.state = "closed"  # closed, open, half-open

    def record_success(self) -> None:
        """Record a successful call, resetting the failure counter."""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        """Record a failed call, potentially opening the circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker '{self.name}' opened after "
                f"{self.failure_count} consecutive failures"
            )

    def is_open(self) -> bool:
        """Check if the circuit is open (should block calls)."""
        if self.state == "open":
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = "half-open"
                return False
            return True
        return False

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = 0.0


# Circuit breakers for each external API
stt_circuit = CircuitBreaker("groq_stt")
llm_circuit = CircuitBreaker("anthropic_llm")
tts_circuit = CircuitBreaker("elevenlabs_tts")

# Fallback responses
STT_FALLBACK = ""
LLM_FALLBACK = "Извините, у меня временные проблемы со связью. Попробуйте снова через минуту."
TTS_FALLBACK = b""


def with_circuit_breaker(
    circuit: CircuitBreaker, fallback: Any
) -> Callable:
    """Decorator that wraps an async function with retry logic and circuit breaker.

    Uses exponential backoff with max 3 retries. If the circuit is open,
    immediately returns the fallback value.
    """

    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        async def _retry_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            if circuit.is_open():
                logger.warning(
                    f"Circuit breaker '{circuit.name}' is open, "
                    f"returning fallback"
                )
                return fallback

            try:
                result = await _retry_wrapper(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception as e:
                circuit.record_failure()
                logger.error(
                    f"Circuit breaker '{circuit.name}' recorded failure: {e}"
                )
                return fallback

        return wrapper

    return decorator
