"""Тесты структурированного логирования и мониторинга."""

import json

import pytest
from aiohttp import web

import logging_config
import sentry_setup
from monitoring import metrics, setup_metrics
from monitoring.endpoint import metrics_handler, setup_metrics_endpoint
from monitoring.middleware import metrics_middleware


class TestStructlogConfiguration:
    """Тесты конфигурации structlog."""

    def test_get_logger_returns_bound_logger(self):
        """get_logger возвращает именованный логгер."""
        logging_config.setup_logging("console")
        log = logging_config.get_logger("test_module")
        assert log is not None

    def test_json_format_produces_valid_json(self, capsys):
        """В JSON-режиме вывод парсится как JSON."""
        logging_config.setup_logging("json")
        log = logging_config.get_logger("test_json")
        log.info("test_event", key="value")
        captured = capsys.readouterr()
        # structlog JSON выводит в stdout
        lines = [line for line in captured.out.strip().split("\n") if line.strip()]
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert parsed["key"] == "value"
        assert "test_event" in parsed.get("event", "") or "test_event" in parsed.get("msg", "")

    def test_console_format_produces_readable_output(self, capsys):
        """В console-режиме вывод содержит читаемый текст."""
        logging_config.setup_logging("console")
        log = logging_config.get_logger("test_console")
        log.info("hello_world", number=42)
        captured = capsys.readouterr()
        assert "hello_world" in captured.out or "42" in captured.out

    def test_setup_logging_does_not_crash(self):
        """setup_logging не падает при повторных вызовах."""
        logging_config.setup_logging("console")
        logging_config.setup_logging("json")
        logging_config.setup_logging("console")


class TestSentrySetup:
    """Тесты Sentry-инициализации."""

    def test_init_sentry_empty_dsn_returns_false(self):
        """Пустой DSN - Sentry не инициализируется."""
        result = sentry_setup.init_sentry("")
        assert result is False

    def test_init_sentry_none_dsn_returns_false(self, monkeypatch):
        """None DSN (SENTRY_DSN не задан) - Sentry не инициализируется."""
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        result = sentry_setup.init_sentry(None)
        assert result is False

    def test_payment_breadcrumb_does_not_crash(self):
        """payment_breadcrumb не падает даже если sentry не инициализирован."""
        sentry_setup.payment_breadcrumb("test_action", amount=100)

    def test_trade_breadcrumb_does_not_crash(self):
        """trade_breadcrumb не падает даже если sentry не инициализирован."""
        sentry_setup.trade_breadcrumb("open", symbol="BTCUSDT", side="Buy")


class TestPrometheusMetrics:
    """Тесты Prometheus-метрик."""

    def test_setup_metrics_does_not_crash(self):
        """setup_metrics() не падает."""
        setup_metrics()

    def test_http_requests_total_increments(self):
        """Counter http_requests_total увеличивается."""
        before = metrics.HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/test", status="200"
        )._value.get()
        metrics.HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/test", status="200"
        ).inc()
        after = metrics.HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/test", status="200"
        )._value.get()
        assert after == before + 1

    def test_payment_events_total_increments(self):
        """Counter payment_events_total увеличивается."""
        metrics.PAYMENT_EVENTS_TOTAL.labels(event_type="invoice_created").inc()
        val = metrics.PAYMENT_EVENTS_TOTAL.labels(
            event_type="invoice_created"
        )._value.get()
        assert val >= 1

    def test_trade_operations_total_increments(self):
        """Counter trade_operations_total увеличивается."""
        metrics.TRADE_OPERATIONS_TOTAL.labels(
            symbol="BTCUSDT", side="Buy", outcome="win"
        ).inc()
        val = metrics.TRADE_OPERATIONS_TOTAL.labels(
            symbol="BTCUSDT", side="Buy", outcome="win"
        )._value.get()
        assert val >= 1

    def test_histogram_observe(self):
        """Histogram http_request_duration_seconds принимает значения."""
        metrics.HTTP_REQUEST_DURATION.labels(
            method="GET", path="/api"
        ).observe(0.123)
        # Не падает - значит работает

    def test_gauge_set(self):
        """Gauge open_positions_count устанавливается."""
        metrics.OPEN_POSITIONS_COUNT.set(3)
        assert metrics.OPEN_POSITIONS_COUNT._value.get() == 3

    def test_queue_length_gauge(self):
        """Gauge queue_length устанавливается."""
        metrics.QUEUE_LENGTH.set(5)
        assert metrics.QUEUE_LENGTH._value.get() == 5


@pytest.mark.asyncio
async def test_metrics_endpoint(aiohttp_client):
    """Endpoint /metrics возвращает text/plain с метриками."""
    app = web.Application()
    setup_metrics_endpoint(app)
    client = await aiohttp_client(app)
    resp = await client.get("/metrics")
    assert resp.status == 200
    text = await resp.text()
    # Проверяем что метрики содержат наши определения
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text


@pytest.mark.asyncio
async def test_metrics_middleware_increments_counter(aiohttp_client):
    """Middleware увеличивает counter при обработке запроса."""
    async def hello(request):
        return web.Response(text="ok")

    app = web.Application(middlewares=[metrics_middleware])
    app.router.add_get("/hello", hello)
    client = await aiohttp_client(app)

    before = metrics.HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/hello", status="200"
    )._value.get()

    resp = await client.get("/hello")
    assert resp.status == 200

    after = metrics.HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="/hello", status="200"
    )._value.get()
    assert after == before + 1
