"""Тесты для структурированного логирования и метрик."""

import json
import logging

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from ai_office.core.logging import (
    StructuredJsonFormatter,
    correlation_id_var,
    agent_context_var,
    get_logger,
    setup_logging,
)
from ai_office.api.observability import MetricsCollector, RequestLoggingMiddleware
from ai_office.api.main import app


# --- StructuredJsonFormatter tests ---


class TestStructuredJsonFormatter:
    """Тесты JSON форматтера."""

    def test_outputs_valid_json(self):
        """StructuredJsonFormatter outputs valid JSON with required keys."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["module"] == "test"
        assert parsed["message"] == "Test message"
        assert "correlation_id" in parsed
        assert "agent_name" in parsed

    def test_includes_correlation_id(self):
        """Formatter includes current correlation_id from contextvars."""
        formatter = StructuredJsonFormatter()
        token = correlation_id_var.set("test-corr-123")
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="msg",
                args=None,
                exc_info=None,
            )
            result = formatter.format(record)
            parsed = json.loads(result)
            assert parsed["correlation_id"] == "test-corr-123"
        finally:
            correlation_id_var.reset(token)

    def test_includes_agent_name(self):
        """Formatter includes current agent_name from contextvars."""
        formatter = StructuredJsonFormatter()
        token = agent_context_var.set("Alice")
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="msg",
                args=None,
                exc_info=None,
            )
            result = formatter.format(record)
            parsed = json.loads(result)
            assert parsed["agent_name"] == "Alice"
        finally:
            agent_context_var.reset(token)

    def test_includes_exception_info(self):
        """Formatter includes exc_info as string when present."""
        formatter = StructuredJsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=None,
            exc_info=exc_info,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert "exc_info" in parsed
        assert "ValueError: test error" in parsed["exc_info"]

    def test_single_line_output(self):
        """Each log entry is a single line (no newlines in output except exc_info value)."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message with\nnewline",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)
        # JSON output should be a single line (newlines in values are escaped)
        assert "\n" not in result


# --- Correlation ID propagation tests ---


class TestCorrelationIdPropagation:
    """Тесты пропагации correlation_id."""

    def test_correlation_id_default_empty(self):
        """Default correlation_id is empty string."""
        assert correlation_id_var.get("") == ""

    def test_correlation_id_set_and_get(self):
        """ContextVar can be set and read."""
        token = correlation_id_var.set("req-abc-123")
        try:
            assert correlation_id_var.get() == "req-abc-123"
        finally:
            correlation_id_var.reset(token)

    def test_agent_context_default_empty(self):
        """Default agent_name is empty string."""
        assert agent_context_var.get("") == ""


# --- MetricsCollector tests ---


class TestMetricsCollector:
    """Тесты MetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Fresh MetricsCollector instance."""
        return MetricsCollector()

    @pytest.mark.asyncio
    async def test_increment_counter(self, collector):
        """Counter increments correctly."""
        await collector.increment_counter("test_counter", labels={"method": "GET"})
        await collector.increment_counter("test_counter", labels={"method": "GET"})
        value = await collector.get_counter("test_counter", labels={"method": "GET"})
        assert value == 2.0

    @pytest.mark.asyncio
    async def test_increment_counter_different_labels(self, collector):
        """Different labels create separate counters."""
        await collector.increment_counter("requests", labels={"method": "GET"})
        await collector.increment_counter("requests", labels={"method": "POST"})
        get_val = await collector.get_counter("requests", labels={"method": "GET"})
        post_val = await collector.get_counter("requests", labels={"method": "POST"})
        assert get_val == 1.0
        assert post_val == 1.0

    @pytest.mark.asyncio
    async def test_observe_histogram(self, collector):
        """Histogram records observations."""
        await collector.observe_histogram("latency", 0.5, labels={"provider": "openai"})
        await collector.observe_histogram("latency", 1.2, labels={"provider": "openai"})
        observations = await collector.get_histogram_observations(
            "latency", labels={"provider": "openai"}
        )
        assert observations == [0.5, 1.2]

    @pytest.mark.asyncio
    async def test_set_gauge(self, collector):
        """Gauge can be set to a value."""
        await collector.set_gauge("active_agents", 5.0)
        val = await collector.get_gauge("active_agents")
        assert val == 5.0

    @pytest.mark.asyncio
    async def test_format_prometheus_counters(self, collector):
        """Prometheus format includes counter metrics."""
        await collector.increment_counter(
            "ai_office_llm_calls_total",
            labels={"provider": "openai", "model": "gpt-4o-mini", "status": "success"},
            value=3.0,
        )
        output = await collector.format_prometheus()
        assert "# TYPE ai_office_llm_calls_total counter" in output
        assert "ai_office_llm_calls_total" in output
        assert "3.0" in output

    @pytest.mark.asyncio
    async def test_format_prometheus_histogram(self, collector):
        """Prometheus format includes histogram buckets."""
        await collector.observe_histogram(
            "ai_office_llm_latency_seconds", 0.3, labels={"provider": "openai"}
        )
        output = await collector.format_prometheus()
        assert "# TYPE ai_office_llm_latency_seconds histogram" in output
        assert "ai_office_llm_latency_seconds_bucket" in output
        assert 'le="0.5"' in output
        assert 'le="+Inf"' in output

    @pytest.mark.asyncio
    async def test_format_prometheus_gauge(self, collector):
        """Prometheus format includes gauge metrics."""
        await collector.set_gauge("ai_office_active_agents", 3.0)
        output = await collector.format_prometheus()
        assert "# TYPE ai_office_active_agents gauge" in output
        assert "ai_office_active_agents 3.0" in output


# --- /api/metrics endpoint tests ---


class TestMetricsEndpoint:
    """Тесты эндпоинта /api/metrics."""

    @pytest_asyncio.fixture
    async def client(self):
        """HTTP client for testing."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, client):
        """GET /api/metrics returns 200."""
        response = await client.get("/api/metrics")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_endpoint_content_type(self, client):
        """GET /api/metrics returns text/plain content type."""
        response = await client.get("/api/metrics")
        assert "text/plain" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_metrics_endpoint_no_auth_required(self, client):
        """GET /api/metrics does not require authentication."""
        # Even without any auth headers, should return 200
        response = await client.get("/api/metrics")
        assert response.status_code == 200


# --- RequestLoggingMiddleware tests ---


class TestRequestLoggingMiddleware:
    """Тесты middleware для логирования запросов."""

    @pytest_asyncio.fixture
    async def client(self):
        """HTTP client for testing."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_adds_request_id_header(self, client):
        """Middleware adds X-Request-ID to response."""
        response = await client.get("/api/health")
        assert "x-request-id" in response.headers

    @pytest.mark.asyncio
    async def test_uses_provided_request_id(self, client):
        """Middleware uses X-Request-ID from request header."""
        response = await client.get(
            "/api/health",
            headers={"X-Request-ID": "custom-id-123"},
        )
        assert response.headers["x-request-id"] == "custom-id-123"

    @pytest.mark.asyncio
    async def test_generates_uuid_if_no_request_id(self, client):
        """Middleware generates UUID if X-Request-ID not provided."""
        response = await client.get("/api/health")
        request_id = response.headers["x-request-id"]
        # UUID format: 8-4-4-4-12 hex chars
        assert len(request_id) == 36
        assert request_id.count("-") == 4


# --- setup_logging tests ---


class TestSetupLogging:
    """Тесты настройки логирования."""

    def test_setup_logging_json(self):
        """setup_logging with json format configures StructuredJsonFormatter."""
        setup_logging(level="DEBUG", log_format="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) > 0
        assert isinstance(root.handlers[0].formatter, StructuredJsonFormatter)

    def test_setup_logging_text(self):
        """setup_logging with text format configures TextFormatter."""
        from ai_office.core.logging import TextFormatter
        setup_logging(level="WARNING", log_format="text")
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert isinstance(root.handlers[0].formatter, TextFormatter)

    def test_get_logger_returns_context_logger(self):
        """get_logger returns a ContextLogger instance."""
        from ai_office.core.logging import ContextLogger
        log = get_logger("test.module")
        assert isinstance(log, ContextLogger)
