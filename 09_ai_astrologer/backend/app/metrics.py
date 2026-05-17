"""Prometheus metrics for AI Astrologer."""

import logging
import time
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)

# Custom metrics
active_calls = Gauge(
    "ai_astrologer_active_calls",
    "Number of currently active call sessions",
)

call_duration_seconds = Histogram(
    "ai_astrologer_call_duration_seconds",
    "Duration of call sessions in seconds",
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600],
)

billing_events_total = Counter(
    "ai_astrologer_billing_events_total",
    "Total billing events",
    ["event_type"],
)

external_api_latency_seconds = Histogram(
    "ai_astrologer_external_api_latency_seconds",
    "Latency of external API calls in seconds",
    ["service"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

external_api_errors_total = Counter(
    "ai_astrologer_external_api_errors_total",
    "Total external API errors",
    ["service"],
)


def create_instrumentator() -> Instrumentator:
    """Create and configure the Prometheus FastAPI instrumentator."""
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/health", "/metrics"],
        env_var_name="ENABLE_METRICS",
    )
    return instrumentator


class APILatencyTracker:
    """Context manager for tracking external API call latency."""

    def __init__(self, service: str):
        self.service = service
        self._start_time: Optional[float] = None

    def __enter__(self):
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._start_time is not None:
            duration = time.time() - self._start_time
            external_api_latency_seconds.labels(service=self.service).observe(duration)
            if exc_type is not None:
                external_api_errors_total.labels(service=self.service).inc()
        return False

    async def __aenter__(self):
        self._start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._start_time is not None:
            duration = time.time() - self._start_time
            external_api_latency_seconds.labels(service=self.service).observe(duration)
            if exc_type is not None:
                external_api_errors_total.labels(service=self.service).inc()
        return False
