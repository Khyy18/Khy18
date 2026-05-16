"""Фикстуры для E2E тестов фриланс-платформ."""

import json
import tempfile

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestServer

from tests.e2e.mock_server import create_mock_app


@pytest_asyncio.fixture
async def mock_server(aiohttp_server):
    """Запуск mock-сервера для тестов."""
    app = create_mock_app()
    server = await aiohttp_server(app)
    return server


@pytest.fixture
def cookies_file(tmp_path):
    """Временный файл cookies для тестов."""
    cookies = [
        {
            "name": "session",
            "value": "test_session_value",
            "domain": "localhost",
            "path": "/",
        }
    ]
    cookies_path = tmp_path / "cookies.json"
    cookies_path.write_text(json.dumps(cookies), encoding="utf-8")
    return str(cookies_path)
