"""Веб-приложение AI-агентства на aiohttp + jinja2."""

import asyncio
import pathlib

from aiohttp import web
import aiohttp_jinja2
import jinja2

import config
from services import SERVICES

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

_HERE = pathlib.Path(__file__).resolve().parent


async def _get_total_orders() -> int:
    """Получить общее количество заказов из БД."""
    if aiosqlite is None:
        return 0
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM orders")
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


async def _get_reviews(limit: int = 10) -> list:
    """Получить 5-звёздочные отзывы из заказов."""
    if aiosqlite is None:
        return []
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, service_type, rating, created_at FROM orders "
                "WHERE rating = 5 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []


async def _get_stats() -> dict:
    """Получить статистику для API."""
    if aiosqlite is None:
        return {"total_orders": 0, "avg_rating": 0, "total_clients": 0}
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM orders")
            row = await cursor.fetchone()
            total_orders = row[0] if row else 0

            cursor = await db.execute(
                "SELECT AVG(rating) FROM orders WHERE rating IS NOT NULL"
            )
            row = await cursor.fetchone()
            avg_rating = round(row[0], 1) if row and row[0] else 0

            cursor = await db.execute("SELECT COUNT(*) FROM clients")
            row = await cursor.fetchone()
            total_clients = row[0] if row else 0

            return {
                "total_orders": total_orders,
                "avg_rating": avg_rating,
                "total_clients": total_clients,
            }
    except Exception:
        return {"total_orders": 0, "avg_rating": 0, "total_clients": 0}


async def index(request: web.Request) -> web.Response:
    """Главная страница - лендинг."""
    total_orders = await _get_total_orders()
    reviews = await _get_reviews(limit=10)

    context = {
        "services": list(SERVICES.values()),
        "bot_username": config.BOT_USERNAME,
        "basic_price": config.SUBSCRIPTION_BASIC_PRICE,
        "basic_orders": config.SUBSCRIPTION_BASIC_ORDERS,
        "pro_price": config.SUBSCRIPTION_PRO_PRICE,
        "total_orders": total_orders,
        "reviews": reviews,
        "google_analytics_id": config.GOOGLE_ANALYTICS_ID,
        "yandex_metrika_id": config.YANDEX_METRIKA_ID,
    }
    return aiohttp_jinja2.render_template("index.html", request, context)


async def health(request: web.Request) -> web.Response:
    """Health-check endpoint."""
    return web.json_response({"status": "ok"})


async def api_stats(request: web.Request) -> web.Response:
    """API endpoint: статистика для лендинга."""
    stats = await _get_stats()
    return web.json_response(stats)


def create_web_app() -> web.Application:
    """Создать и настроить aiohttp-приложение."""
    app = web.Application()

    # Настройка jinja2
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(_HERE / "templates")),
    )

    # Маршруты
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/stats", api_stats)

    # Статические файлы
    app.router.add_static("/static/", path=str(_HERE / "static"), name="static")

    return app


async def start_web_app() -> None:
    """Запустить веб-сервер (блокирует до завершения)."""
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.WEB_HOST, config.WEB_PORT)
    await site.start()
    # Keep the process alive until cancelled
    await asyncio.Event().wait()
