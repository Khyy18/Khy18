"""Tests for core/resilience.py - Circuit breaker and graceful degradation."""
from __future__ import annotations

import asyncio
import time

import pytest

from core.resilience import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
    GracefulDegradation,
)


# ---------- CircuitBreaker Tests ----------


@pytest.mark.asyncio
async def test_circuit_breaker_starts_closed():
    """Circuit breaker should start in CLOSED state."""
    cb = CircuitBreaker(service_name="test_service")
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available is True
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures():
    """Circuit should transition to OPEN after 5 consecutive failures."""
    cb = CircuitBreaker(service_name="test_service", failure_threshold=5)

    for _ in range(5):
        cb.record_failure()

    assert cb.state == CircuitState.OPEN
    assert cb.is_available is False
    assert cb.failure_count == 5


@pytest.mark.asyncio
async def test_circuit_half_open_after_timeout():
    """Circuit should transition to HALF_OPEN after recovery_timeout elapses."""
    cb = CircuitBreaker(
        service_name="test_service", failure_threshold=5, recovery_timeout=60.0
    )

    # Open the circuit
    for _ in range(5):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Simulate that last_failure_time was 61 seconds ago
    cb.last_failure_time = time.time() - 61.0

    assert cb.state == CircuitState.HALF_OPEN
    assert cb.is_available is True


@pytest.mark.asyncio
async def test_circuit_closes_on_success_in_half_open():
    """Circuit should close on a successful call in HALF_OPEN state."""
    cb = CircuitBreaker(
        service_name="test_service", failure_threshold=5, recovery_timeout=60.0
    )

    # Open the circuit
    for _ in range(5):
        cb.record_failure()

    # Transition to HALF_OPEN
    cb.last_failure_time = time.time() - 61.0
    assert cb.state == CircuitState.HALF_OPEN

    # Record success
    cb.record_success()

    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_reopens_on_failure_in_half_open():
    """Circuit should reopen on failure in HALF_OPEN state."""
    cb = CircuitBreaker(
        service_name="test_service", failure_threshold=5, recovery_timeout=60.0
    )

    # Open the circuit
    for _ in range(5):
        cb.record_failure()

    # Transition to HALF_OPEN
    cb.last_failure_time = time.time() - 61.0
    assert cb.state == CircuitState.HALF_OPEN

    # Record failure - should reopen
    cb.record_failure()

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_call_success():
    """call() should execute coroutine and record success."""
    cb = CircuitBreaker(service_name="test_service")

    async def success_coro():
        return "ok"

    result = await cb.call(success_coro())
    assert result == "ok"
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_call_failure():
    """call() should record failure on exception."""
    cb = CircuitBreaker(service_name="test_service", failure_threshold=2)

    async def fail_coro():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await cb.call(fail_coro())

    assert cb.failure_count == 1

    with pytest.raises(ValueError, match="boom"):
        await cb.call(fail_coro())

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_call_raises_when_open():
    """call() should raise CircuitOpenError when circuit is OPEN."""
    cb = CircuitBreaker(service_name="test_service", failure_threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    async def dummy_coro():
        return "should not run"

    with pytest.raises(CircuitOpenError) as exc_info:
        await cb.call(dummy_coro())

    assert exc_info.value.service_name == "test_service"


# ---------- GracefulDegradation Tests ----------


@pytest.mark.asyncio
async def test_graceful_degradation_fallback_modes():
    """GracefulDegradation should return correct fallback for each service."""
    registry = CircuitBreakerRegistry()
    gd = GracefulDegradation(registry)

    redis_fallback = gd.get_fallback_mode("redis")
    assert redis_fallback["mode"] == "in_memory_cache"
    assert "rate limiting disabled" in redis_fallback["description"]

    llm_fallback = gd.get_fallback_mode("llm")
    assert llm_fallback["mode"] == "template_only"
    assert "template" in llm_fallback["description"]

    smtp_fallback = gd.get_fallback_mode("smtp")
    assert smtp_fallback["mode"] == "queue_retry"
    assert "retry" in smtp_fallback["description"]

    linkedin_fallback = gd.get_fallback_mode("linkedin")
    assert linkedin_fallback["mode"] == "email_only"
    assert "email-only" in linkedin_fallback["description"]

    postgres_fallback = gd.get_fallback_mode("postgres")
    assert postgres_fallback["mode"] == "service_unavailable"
    assert "unavailable" in postgres_fallback["description"]

    # Unknown service
    unknown_fallback = gd.get_fallback_mode("unknown_service")
    assert unknown_fallback["mode"] == "unknown"


# ---------- CircuitBreakerRegistry Tests ----------


@pytest.mark.asyncio
async def test_registry_get_or_create():
    """Registry should create new breakers and return existing ones."""
    registry = CircuitBreakerRegistry()

    # First call creates
    cb1 = registry.get_or_create("redis", failure_threshold=3, recovery_timeout=30.0)
    assert isinstance(cb1, CircuitBreaker)
    assert cb1.state == CircuitState.CLOSED

    # Second call returns same instance
    cb2 = registry.get_or_create("redis", failure_threshold=10, recovery_timeout=120.0)
    assert cb2 is cb1

    # Different service creates new
    cb3 = registry.get_or_create("postgres")
    assert cb3 is not cb1


@pytest.mark.asyncio
async def test_registry_get_all_status():
    """Registry.get_all_status() should return status of all breakers."""
    registry = CircuitBreakerRegistry()
    registry.get_or_create("redis")
    registry.get_or_create("postgres")

    # Record some failures on redis
    redis_cb = registry.get_or_create("redis")
    for _ in range(5):
        redis_cb.record_failure()

    status = registry.get_all_status()
    assert "redis" in status
    assert "postgres" in status
    assert status["redis"]["state"] == "open"
    assert status["redis"]["failure_count"] == 5
    assert status["postgres"]["state"] == "closed"
    assert status["postgres"]["is_available"] is True
