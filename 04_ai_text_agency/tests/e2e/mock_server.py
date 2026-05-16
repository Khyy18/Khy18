"""Mock-сервер для E2E тестов фриланс-платформ."""

from aiohttp import web

KWORK_PROJECTS_HTML = """<!DOCTYPE html>
<html>
<body>
<div class="card__content">
    <div class="wants-card__header-title">
        <a href="/projects/test-project-1">Разработка Telegram бота</a>
    </div>
    <div class="wants-card__description-text">
        Нужен бот для автоматизации продаж
    </div>
    <div class="wants-card__header-price">
        <span class="amount">5000</span>
    </div>
</div>
<div class="card__content">
    <div class="wants-card__header-title">
        <a href="/projects/test-project-2">Парсер данных на Python</a>
    </div>
    <div class="wants-card__description-text">
        Парсинг сайтов с использованием Scrapy
    </div>
    <div class="wants-card__header-price">
        <span class="amount">3000</span>
    </div>
</div>
</body>
</html>"""

KWORK_PROJECT_DETAIL_HTML = """<!DOCTYPE html>
<html>
<body>
<h1>Разработка Telegram бота</h1>
<div class="wants-offer-form">
    <textarea name="description" placeholder="Опишите ваше предложение"></textarea>
    <button type="submit">Отправить отклик</button>
</div>
</body>
</html>"""

FLRU_PROJECTS_HTML = """<!DOCTYPE html>
<html>
<body>
<div id="projects-list">
    <div class="b-post">
        <div class="b-post__title">
            <a href="/projects/fl-project-1">Создание веб-приложения</a>
        </div>
        <div class="b-post__body">
            Веб-приложение на Django с REST API
        </div>
        <div class="b-post__price">
            <span class="count">15000</span>
        </div>
    </div>
    <div class="b-post">
        <div class="b-post__title">
            <a href="/projects/fl-project-2">Мобильное приложение</a>
        </div>
        <div class="b-post__body">
            Приложение на Flutter для iOS и Android
        </div>
        <div class="b-post__price">
            <span class="count">50000</span>
        </div>
    </div>
</div>
</body>
</html>"""

FLRU_PROJECT_DETAIL_HTML = """<!DOCTYPE html>
<html>
<body>
<h1>Создание веб-приложения</h1>
<div class="b-post__form">
    <textarea name="response" placeholder="Ваш отклик"></textarea>
    <button type="submit">Откликнуться</button>
</div>
</body>
</html>"""


def create_mock_app() -> web.Application:
    """Создать aiohttp приложение с mock-маршрутами."""
    app = web.Application()
    app.router.add_get("/kwork/projects", handle_kwork_projects)
    app.router.add_get("/kwork/projects/{project_id}", handle_kwork_project_detail)
    app.router.add_get("/flru/projects/", handle_flru_projects)
    app.router.add_get("/flru/projects/{project_id}", handle_flru_project_detail)
    # Корневые маршруты для login
    app.router.add_get("/kwork/", handle_kwork_root)
    app.router.add_get("/flru/", handle_flru_root)
    return app


async def handle_kwork_root(request: web.Request) -> web.Response:
    return web.Response(text="<html><body>Kwork.ru</body></html>", content_type="text/html")


async def handle_flru_root(request: web.Request) -> web.Response:
    return web.Response(text="<html><body>FL.ru</body></html>", content_type="text/html")


async def handle_kwork_projects(request: web.Request) -> web.Response:
    return web.Response(text=KWORK_PROJECTS_HTML, content_type="text/html")


async def handle_kwork_project_detail(request: web.Request) -> web.Response:
    return web.Response(text=KWORK_PROJECT_DETAIL_HTML, content_type="text/html")


async def handle_flru_projects(request: web.Request) -> web.Response:
    return web.Response(text=FLRU_PROJECTS_HTML, content_type="text/html")


async def handle_flru_project_detail(request: web.Request) -> web.Response:
    return web.Response(text=FLRU_PROJECT_DETAIL_HTML, content_type="text/html")
