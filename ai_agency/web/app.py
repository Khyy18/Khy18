"""Веб-приложение AI-агентства на aiohttp + jinja2."""

import pathlib

from aiohttp import web
import aiohttp_jinja2
import jinja2

import config
from services import SERVICES


_HERE = pathlib.Path(__file__).resolve().parent


async def index(request: web.Request) -> web.Response:
    """Главная страница - лендинг."""
    context = {
        "services": list(SERVICES.values()),
        "bot_username": config.BOT_USERNAME,
        "basic_price": config.SUBSCRIPTION_BASIC_PRICE,
        "basic_orders": config.SUBSCRIPTION_BASIC_ORDERS,
        "pro_price": config.SUBSCRIPTION_PRO_PRICE,
    }
    return aiohttp_jinja2.render_template("index.html", request, context)


async def health(request: web.Request) -> web.Response:
    """Health-check endpoint."""
    return web.json_response({"status": "ok"})


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

    # Статические файлы
    app.router.add_static("/static/", path=str(_HERE / "static"), name="static")

    return app


async def start_web_app() -> None:
    """Запустить веб-сервер."""
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.WEB_HOST, config.WEB_PORT)
    await site.start()
