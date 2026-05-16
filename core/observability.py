"""Observability infrastructure: structured logging, Prometheus metrics, Sentry, and correlation IDs."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# --- Correlation ID context ---

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


# --- Structured Logging ---


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON output, timestamps, and correlation_id."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# --- Prometheus Metrics ---

emails_sent_total = Counter(
    "emails_sent_total",
    "Total number of emails sent successfully",
)

emails_failed_total = Counter(
    "emails_failed_total",
    "Total number of emails that failed to send",
)

linkedin_actions_total = Counter(
    "linkedin_actions_total",
    "Total LinkedIn actions performed",
    ["action"],
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests made",
    ["provider", "model"],
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM request latency in seconds",
    ["provider"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

llm_errors_total = Counter(
    "llm_errors_total",
    "Total LLM request errors",
    ["provider"],
)

sequence_ticks_total = Counter(
    "sequence_ticks_total",
    "Total sequence runner ticks executed",
)

replies_processed_total = Counter(
    "replies_processed_total",
    "Total replies processed by conversation agent",
)

active_campaigns_gauge = Gauge(
    "active_campaigns_gauge",
    "Number of currently active campaigns",
)

fallback_triggered_total = Counter(
    "fallback_triggered_total",
    "Total LLM fallback triggers",
    ["provider"],
)


# --- Sentry ---


def setup_sentry(dsn: str) -> None:
    """Initialize Sentry SDK if DSN is provided."""
    if not dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
        ],
        traces_sample_rate=0.1,
    )


# --- Correlation ID Middleware ---


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that generates a correlation ID for each request and binds it to structlog context."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        correlation_id_var.set(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=request_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request_id
        return response


# --- Metrics Endpoint ---


def metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
