"""Модуль мониторинга: Prometheus-метрики, middleware, /metrics endpoint."""

from monitoring.metrics import (
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
    OPEN_POSITIONS_COUNT,
    PAYMENT_EVENTS_TOTAL,
    QUEUE_LENGTH,
    TRADE_OPERATIONS_TOTAL,
    TRADE_PNL_DISTRIBUTION,
)


def setup_metrics() -> None:
    """Инициализировать метрики (no-op, метрики создаются при импорте модуля)."""
    # Prometheus-client создаёт метрики при определении. Этот вызов
    # гарантирует что модуль metrics загружен.
    pass
