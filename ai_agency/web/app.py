"""Веб-приложение AI-агентства на aiohttp + jinja2."""

import asyncio
import base64
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

# Интеграция realtime_dashboard (graceful)
try:
    import realtime_dashboard
except ImportError:
    realtime_dashboard = None

_HERE = pathlib.Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent


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


def _check_admin_auth(request: web.Request) -> bool:
    """Check basic auth for admin routes."""
    if not config.ADMIN_DASHBOARD_PASSWORD:
        return True  # No password set = open access (dev mode)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        _, password = decoded.split(":", 1)
        return password == config.ADMIN_DASHBOARD_PASSWORD
    except Exception:
        return False


async def admin_dashboard(request: web.Request) -> web.Response:
    """Admin dashboard page with basic auth."""
    if not _check_admin_auth(request):
        return web.Response(
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Admin"'},
            text="Unauthorized",
        )
    return aiohttp_jinja2.render_template("admin_dashboard.html", request, {})


async def api_admin_metrics(request: web.Request) -> web.Response:
    """API: admin metrics (orders today, revenue, clients, etc.)."""
    if not _check_admin_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    if aiosqlite is None:
        return web.json_response({})

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            from datetime import datetime, timedelta

            today = datetime.utcnow().strftime("%Y-%m-%d")

            # Orders today
            cursor = await db.execute(
                "SELECT COUNT(*), COALESCE(SUM(price), 0) FROM orders WHERE DATE(created_at) = ?",
                (today,),
            )
            row = await cursor.fetchone()
            orders_today = row[0] if row else 0
            revenue_today = row[1] if row else 0

            # Total clients
            cursor = await db.execute("SELECT COUNT(*) FROM clients")
            row = await cursor.fetchone()
            total_clients = row[0] if row else 0

            # Avg rating
            cursor = await db.execute(
                "SELECT AVG(rating) FROM orders WHERE rating IS NOT NULL"
            )
            row = await cursor.fetchone()
            avg_rating = round(row[0], 1) if row and row[0] else 0

            # Revenue by day (last 7 days)
            since = (datetime.utcnow() - timedelta(days=7)).isoformat()
            cursor = await db.execute(
                """SELECT DATE(created_at) as day, COALESCE(SUM(price), 0)
                   FROM orders WHERE created_at >= ? AND status = 'completed'
                   GROUP BY DATE(created_at) ORDER BY day""",
                (since,),
            )
            revenue_by_day = [(row[0], row[1]) for row in await cursor.fetchall()]

            # Orders by service
            cursor = await db.execute(
                """SELECT service_type, COUNT(*) FROM orders
                   GROUP BY service_type ORDER BY COUNT(*) DESC LIMIT 10"""
            )
            orders_by_service = [(row[0], row[1]) for row in await cursor.fetchall()]

            return web.json_response({
                "orders_today": orders_today,
                "revenue_today": revenue_today,
                "total_clients": total_clients,
                "avg_rating": avg_rating,
                "revenue_by_day": revenue_by_day,
                "orders_by_service": orders_by_service,
            })
    except Exception:
        return web.json_response({})


async def api_admin_orders(request: web.Request) -> web.Response:
    """API: recent orders for admin."""
    if not _check_admin_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    if aiosqlite is None:
        return web.json_response([])

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT 20"
            )
            rows = await cursor.fetchall()
            return web.json_response([dict(row) for row in rows])
    except Exception:
        return web.json_response([])


async def api_admin_promos(request: web.Request) -> web.Response:
    """API: active promos for admin."""
    if not _check_admin_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    if aiosqlite is None:
        return web.json_response([])

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM promo_codes WHERE active = 1 ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return web.json_response([dict(row) for row in rows])
    except Exception:
        return web.json_response([])


async def api_admin_expenses(request: web.Request) -> web.Response:
    """API: recent expenses for admin."""
    if not _check_admin_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    if aiosqlite is None:
        return web.json_response([])

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM expenses ORDER BY created_at DESC LIMIT 20"
            )
            rows = await cursor.fetchall()
            return web.json_response([dict(row) for row in rows])
    except Exception:
        return web.json_response([])


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

    # Admin dashboard routes
    app.router.add_get("/admin", admin_dashboard)
    app.router.add_get("/api/admin/metrics", api_admin_metrics)
    app.router.add_get("/api/admin/orders", api_admin_orders)
    app.router.add_get("/api/admin/promos", api_admin_promos)
    app.router.add_get("/api/admin/expenses", api_admin_expenses)

    # WebSocket real-time dashboard
    if realtime_dashboard:
        app.router.add_get("/ws/dashboard", realtime_dashboard.websocket_handler)

    # Статические файлы
    app.router.add_static("/static/", path=str(_HERE / "static"), name="static")

    # Mini App static files
    mini_app_path = _PROJECT_ROOT / "mini_app"
    if mini_app_path.exists():
        app.router.add_static("/miniapp/", path=str(mini_app_path), name="miniapp")

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
