"""Фикстуры для E2E тестов фриланс-платформ."""

import json
import subprocess
import tempfile

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestServer

from tests.e2e.mock_server import create_mock_app


def _browser_binary_works() -> bool:
    """Check if Playwright Chromium binary is functional."""
    try:
        import pathlib
        cache_dir = pathlib.Path.home() / ".cache" / "ms-playwright"
        if not cache_dir.exists():
            return False
        # Find chrome-headless-shell binary and try to execute it
        for binary in cache_dir.rglob("chrome-headless-shell"):
            if binary.is_file():
                result = subprocess.run(
                    [str(binary), "--version"],
                    capture_output=True,
                    timeout=5,
                )
                return result.returncode == 0
        return False
    except Exception:
        return False


_BROWSER_AVAILABLE = _browser_binary_works()


@pytest.fixture(autouse=True)
def _skip_if_no_browser():
    """Skip e2e tests if browser binary is not functional."""
    if not _BROWSER_AVAILABLE:
        pytest.skip("Playwright browser binary not functional (missing system libraries)")


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
