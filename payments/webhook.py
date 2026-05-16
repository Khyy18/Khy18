"""Webhook-обработчик для Telegram-обновлений (aiohttp)."""

from __future__ import annotations

import os

from aiohttp import web

from payments.service import PaymentService
from rate_limiter.middleware import RateLimiterMiddleware


def setup_routes(
    app: web.Application,
    payment_service: PaymentService,
    secret_token: str | None = None,
) -> None:
    """Зарегистрировать маршрут webhook в aiohttp-приложении."""
    app["payment_service"] = payment_service
    # Use provided secret_token or fall back to env var
    app["webhook_secret"] = secret_token or os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    app.router.add_post("/webhook/telegram", _handle_update)
    # Применяем rate limiter middleware
    rate_limiter = RateLimiterMiddleware()
    app.middlewares.append(rate_limiter.middleware)


async def _handle_update(request: web.Request) -> web.Response:
    """Обработать входящий Telegram update (pre_checkout_query / successful_payment)."""
    # Validate secret token if configured
    webhook_secret = request.app.get("webhook_secret", "")
    if webhook_secret:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_token != webhook_secret:
            return web.Response(status=403, text="forbidden")

    try:
        update = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    payment_service: PaymentService = request.app["payment_service"]

    # pre_checkout_query
    pre_checkout = update.get("pre_checkout_query")
    if pre_checkout:
        query_id = pre_checkout.get("id", "")
        invoice_payload = pre_checkout.get("invoice_payload", "")
        # Используем aiohttp session из приложения или создаём временную
        session = request.app.get("http_session")
        if session:
            await payment_service.handle_pre_checkout_query(
                session, query_id, invoice_payload
            )
        return web.Response(status=200, text="ok")

    # successful_payment
    message = update.get("message", {})
    if message.get("successful_payment"):
        session = request.app.get("http_session")
        await payment_service.handle_successful_payment(update, session=session)
        return web.Response(status=200, text="ok")

    return web.Response(status=200, text="ok")
