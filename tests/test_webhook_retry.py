"""Тесты для payments/retry.py: WebhookRetryQueue, backoff, DLQ."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payments.retry import (
    BASE_DELAY_SEC,
    MAX_ATTEMPTS,
    WebhookPayload,
    WebhookRetryQueue,
)


def _make_mock_session(status_codes):
    """Создать мок-сессию с заданными HTTP-статусами ответов."""
    mock_session = MagicMock()
    responses = []
    for status in status_codes:
        mock_resp = MagicMock()
        mock_resp.status = status
        responses.append(mock_resp)

    call_count = {"i": 0}

    @asynccontextmanager
    async def _post(*args, **kwargs):
        idx = min(call_count["i"], len(responses) - 1)
        call_count["i"] += 1
        yield responses[idx]

    mock_session.post = _post
    return mock_session


def _make_error_session(error):
    """Создать мок-сессию, которая бросает ошибку."""
    mock_session = MagicMock()

    @asynccontextmanager
    async def _post(*args, **kwargs):
        raise error
        yield  # noqa: F841

    mock_session.post = _post
    return mock_session


def test_enqueue():
    """enqueue добавляет элемент в очередь."""
    queue = WebhookRetryQueue()
    queue.enqueue({"event": "payment"}, "https://example.com/webhook")

    assert queue.pending_count == 1
    assert queue.dlq_count == 0


def test_backoff_delays():
    """Экспоненциальный backoff: 1, 2, 4, 8, 16."""
    queue = WebhookRetryQueue()

    assert queue.get_backoff_delay(0) == 1.0
    assert queue.get_backoff_delay(1) == 2.0
    assert queue.get_backoff_delay(2) == 4.0
    assert queue.get_backoff_delay(3) == 8.0
    assert queue.get_backoff_delay(4) == 16.0


@pytest.mark.asyncio
async def test_process_one_success():
    """Успешная отправка с первой попытки."""
    queue = WebhookRetryQueue()
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_mock_session([200])
    result = await queue.process_one(mock_session, item)
    assert result is True
    assert queue.dlq_count == 0


@pytest.mark.asyncio
async def test_process_one_to_dlq():
    """После MAX_ATTEMPTS неудач - в DLQ."""
    queue = WebhookRetryQueue()
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_mock_session([500] * MAX_ATTEMPTS)

    with patch("payments.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await queue.process_one(mock_session, item)

    assert result is False
    assert queue.dlq_count == 1
    assert queue.dead_letter_queue[0].callback_url == "https://example.com/hook"
    assert item.attempt == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_process_one_retry_then_success():
    """Неудача на первой попытке, успех на второй."""
    queue = WebhookRetryQueue()
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_mock_session([500, 200])

    with patch("payments.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await queue.process_one(mock_session, item)

    assert result is True
    assert queue.dlq_count == 0


@pytest.mark.asyncio
async def test_process_all():
    """process_all обрабатывает всю очередь."""
    queue = WebhookRetryQueue()
    queue.enqueue({"event": "a"}, "https://example.com/a")
    queue.enqueue({"event": "b"}, "https://example.com/b")

    mock_session = _make_mock_session([200, 200])

    results = await queue.process_all(mock_session)
    assert results["success"] == 2
    assert results["dlq"] == 0
    assert queue.pending_count == 0


@pytest.mark.asyncio
async def test_network_error_retries():
    """Сетевая ошибка обрабатывается как неудача."""
    import aiohttp

    queue = WebhookRetryQueue()
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_error_session(aiohttp.ClientError("Connection refused"))

    with patch("payments.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await queue.process_one(mock_session, item)

    assert result is False
    assert queue.dlq_count == 1
