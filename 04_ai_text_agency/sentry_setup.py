"""Инициализация Sentry SDK для отслеживания ошибок.

Если переменная окружения SENTRY_DSN пуста или не задана,
Sentry не инициализируется и бот работает без внешнего мониторинга ошибок.
"""

from __future__ import annotations

import os


def init_sentry(dsn: str | None = None) -> bool:
    """Инициализировать Sentry SDK.

    Args:
        dsn: DSN проекта Sentry. Если None, берётся из SENTRY_DSN env var.

    Returns:
        True если Sentry успешно инициализирован, False если пропущен.
    """
    sentry_dsn = dsn or os.getenv("SENTRY_DSN", "")
    if not sentry_dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,
        attach_stacktrace=True,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
    )
    return True


def payment_breadcrumb(action: str, **kwargs) -> None:
    """Добавить breadcrumb для платёжных операций."""
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            category="payment",
            message=action,
            data=kwargs,
            level="info",
        )
    except Exception:
        pass


def trade_breadcrumb(action: str, **kwargs) -> None:
    """Добавить breadcrumb для торговых операций."""
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            category="trade",
            message=action,
            data=kwargs,
            level="info",
        )
    except Exception:
        pass
