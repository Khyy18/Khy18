"""Тесты для payments/retry.py: WebhookRetryQueue, backoff, DLQ."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from payments.retry import (
    BASE_DELAY_SEC,
    MAX_ATTEMPTS,
    WebhookPayload,
    WebhookRetryQueue,
    get_dlq_items,
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


def test_enqueue(tmp_path):
    """enqueue добавляет элемент в очередь."""
    db_path = str(tmp_path / "dlq.db")
    queue = WebhookRetryQueue(dlq_db_path=db_path)
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
async def test_process_one_success(tmp_path):
    """Успешная отправка с первой попытки."""
    db_path = str(tmp_path / "dlq.db")
    queue = WebhookRetryQueue(dlq_db_path=db_path)
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_mock_session([200])
    result = await queue.process_one(mock_session, item)
    assert result is True
    assert queue.dlq_count == 0


@pytest.mark.asyncio
async def test_process_one_to_dlq(tmp_path):
    """После MAX_ATTEMPTS неудач - в DLQ."""
    db_path = str(tmp_path / "dlq.db")
    queue = WebhookRetryQueue(dlq_db_path=db_path)
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_mock_session([500] * MAX_ATTEMPTS)

    with patch("payments.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await queue.process_one(mock_session, item)

    assert result is False
    assert queue.dlq_count == 1
    dlq_items = get_dlq_items(db_path)
    assert dlq_items[0]["callback_url"] == "https://example.com/hook"
    assert item.attempt == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_process_one_retry_then_success(tmp_path):
    """Неудача на первой попытке, успех на второй."""
    db_path = str(tmp_path / "dlq.db")
    queue = WebhookRetryQueue(dlq_db_path=db_path)
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
async def test_process_all(tmp_path):
    """process_all обрабатывает всю очередь."""
    db_path = str(tmp_path / "dlq.db")
    queue = WebhookRetryQueue(dlq_db_path=db_path)
    queue.enqueue({"event": "a"}, "https://example.com/a")
    queue.enqueue({"event": "b"}, "https://example.com/b")

    mock_session = _make_mock_session([200, 200])

    results = await queue.process_all(mock_session)
    assert results["success"] == 2
    assert results["dlq"] == 0
    assert queue.pending_count == 0


@pytest.mark.asyncio
async def test_network_error_retries(tmp_path):
    """Сетевая ошибка обрабатывается как неудача."""
    import aiohttp

    db_path = str(tmp_path / "dlq.db")
    queue = WebhookRetryQueue(dlq_db_path=db_path)
    item = WebhookPayload(
        payload={"event": "test"},
        callback_url="https://example.com/hook",
    )

    mock_session = _make_error_session(aiohttp.ClientError("Connection refused"))

    with patch("payments.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await queue.process_one(mock_session, item)

    assert result is False
    assert queue.dlq_count == 1
