"""Webhook-обработчик для Telegram-обновлений (aiohttp)."""

from __future__ import annotations

from aiohttp import web

from payments.service import PaymentService


def setup_routes(app: web.Application, payment_service: PaymentService) -> None:
    """Зарегистрировать маршрут webhook в aiohttp-приложении."""
    app["payment_service"] = payment_service
    app.router.add_post("/webhook/telegram", _handle_update)


async def _handle_update(request: web.Request) -> web.Response:
    """Обработать входящий Telegram update (pre_checkout_query / successful_payment)."""
    try:
        update = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    payment_service: PaymentService = request.app["payment_service"]

    # pre_checkout_query
    pre_checkout = update.get("pre_checkout_query")
    if pre_checkout:
        query_id = pre_checkout.get("id", "")
        # Используем aiohttp session из приложения или создаём временную
        session = request.app.get("http_session")
        if session:
            await payment_service.handle_pre_checkout_query(session, query_id)
        return web.Response(status=200, text="ok")

    # successful_payment
    message = update.get("message", {})
    if message.get("successful_payment"):
        await payment_service.handle_successful_payment(update)
        return web.Response(status=200, text="ok")

    return web.Response(status=200, text="ok")
