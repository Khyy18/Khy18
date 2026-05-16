"""Тесты Telegram initData validation middleware."""

import hashlib
import hmac
from unittest.mock import patch
from urllib.parse import quote

import pytest
from httpx import AsyncClient

from ai_office.api.middleware import TelegramAuthMiddleware


TEST_BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"


def make_init_data(params: dict, bot_token: str = TEST_BOT_TOKEN) -> str:
    """Создать валидный initData с корректным hash."""
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    hash_value = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    params_with_hash = {**params, "hash": hash_value}
    return "&".join(f"{k}={v}" for k, v in params_with_hash.items())


def test_validate_init_data_valid():
    """Тест валидации корректного initData."""
    params = {
        "user": '{"id":123456,"first_name":"Test"}',
        "auth_date": "1234567890",
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
    }
    init_data = make_init_data(params)
    with patch("ai_office.api.middleware.settings") as mock_settings:
        mock_settings.telegram_bot_token = TEST_BOT_TOKEN
        result = TelegramAuthMiddleware.validate_init_data(init_data)
    assert result is True


def test_validate_init_data_invalid_hash():
    """Тест валидации с некорректным hash."""
    init_data = "user=test&auth_date=123&hash=invalid_hash_value"
    with patch("ai_office.api.middleware.settings") as mock_settings:
        mock_settings.telegram_bot_token = TEST_BOT_TOKEN
        result = TelegramAuthMiddleware.validate_init_data(init_data)
    assert result is False


def test_validate_init_data_no_hash():
    """Тест валидации без hash."""
    init_data = "user=test&auth_date=123"
    with patch("ai_office.api.middleware.settings") as mock_settings:
        mock_settings.telegram_bot_token = TEST_BOT_TOKEN
        result = TelegramAuthMiddleware.validate_init_data(init_data)
    assert result is False


@pytest.mark.asyncio
async def test_middleware_skips_health(test_client: AsyncClient):
    """Тест что middleware пропускает /api/health."""
    response = await test_client.get("/api/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_blocks_without_init_data(test_client: AsyncClient):
    """Тест что middleware блокирует запросы без initData когда auth включен."""
    with patch("ai_office.api.middleware.settings") as mock_settings:
        mock_settings.skip_telegram_auth = False
        mock_settings.telegram_bot_token = TEST_BOT_TOKEN
        response = await test_client.get("/api/agents")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing initData"


@pytest.mark.asyncio
async def test_middleware_allows_with_valid_init_data(test_client: AsyncClient):
    """Тест что middleware пропускает запросы с валидным initData."""
    params = {
        "user": '{"id":123456,"first_name":"Test"}',
        "auth_date": "1234567890",
    }
    with patch("ai_office.api.middleware.settings") as mock_settings:
        mock_settings.skip_telegram_auth = False
        mock_settings.telegram_bot_token = TEST_BOT_TOKEN
        init_data = make_init_data(params, TEST_BOT_TOKEN)
        response = await test_client.get(
            "/api/agents",
            headers={"X-Telegram-Init-Data": init_data},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_dev_mode_skips_auth(test_client: AsyncClient):
    """Тест что middleware пропускает проверку в dev-режиме."""
    # По умолчанию skip_telegram_auth=True (conftest не меняет)
    response = await test_client.get("/api/agents")
    assert response.status_code == 200
