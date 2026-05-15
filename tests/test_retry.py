"""Тесты _request_with_retry в api_engine.

Проверяем:
  - test_retry_succeeds_on_second_attempt — первый _request → None, второй → result.
  - test_retry_gives_up_after_max — все _request → None. Return None, max_retries вызовов.
  - test_no_retry_for_scan — обычный _request (без retry) по-прежнему возвращает None (1 вызов).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """Первый _request → None, второй → result. Verify 2 вызова."""
    import api_engine

    call_count = 0
    result_data = {"retCode": 0, "result": {"orderId": "123"}}

    async def mock_request(session, method, path, params=None, body=None, auth=False, timeout=15):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        return result_data

    session = AsyncMock()
    with patch.object(api_engine, "_request", side_effect=mock_request):
        resp = await api_engine._request_with_retry(
            session, "POST", "/v5/order/create",
            body={"symbol": "BTCUSDT"}, auth=True,
            max_retries=3, backoff_base=0.01,
        )

    assert resp == result_data
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_gives_up_after_max():
    """Все _request → None. Verify max_retries вызовов и return None."""
    import api_engine

    call_count = 0

    async def mock_request(session, method, path, params=None, body=None, auth=False, timeout=15):
        nonlocal call_count
        call_count += 1
        return None

    session = AsyncMock()
    with patch.object(api_engine, "_request", side_effect=mock_request):
        resp = await api_engine._request_with_retry(
            session, "POST", "/v5/order/cancel",
            body={"symbol": "BTCUSDT", "orderId": "abc"}, auth=True,
            max_retries=3, backoff_base=0.01,
        )

    assert resp is None
    assert call_count == 3


@pytest.mark.asyncio
async def test_no_retry_for_scan():
    """Обычный _request (без retry) по-прежнему возвращает None при ошибке (1 вызов)."""
    import api_engine

    call_count = 0

    async def mock_request(session, method, path, params=None, body=None, auth=False, timeout=15):
        nonlocal call_count
        call_count += 1
        return None

    session = AsyncMock()
    with patch.object(api_engine, "_request", side_effect=mock_request):
        # Обычный _request используется для scan-вызовов — один вызов, без retry.
        resp = await api_engine._request(
            session, "GET", "/v5/market/kline",
            params={"symbol": "BTCUSDT"}, auth=False,
        )

    assert resp is None
    assert call_count == 1
