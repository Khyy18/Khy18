"""Tests for retry_request from arbitrage.retry (use aioresponses to mock HTTP)."""

from __future__ import annotations

import pytest
import aiohttp
from aioresponses import aioresponses

from arbitrage.retry import retry_request


@pytest.mark.asyncio
async def test_successful_request() -> None:
    """200 returned immediately."""
    with aioresponses() as m:
        m.get("http://example.com/api", payload={"ok": True}, status=200)
        async with aiohttp.ClientSession() as session:
            resp = await retry_request(session, "GET", "http://example.com/api", max_retries=3)
            assert resp.status == 200
            data = await resp.json()
            assert data == {"ok": True}


@pytest.mark.asyncio
async def test_5xx_retries() -> None:
    """First 500, then 200 (2 calls made)."""
    with aioresponses() as m:
        m.get("http://example.com/api", status=500)
        m.get("http://example.com/api", payload={"ok": True}, status=200)
        async with aiohttp.ClientSession() as session:
            resp = await retry_request(
                session, "GET", "http://example.com/api",
                max_retries=3, backoff_base=0.01,
            )
            assert resp.status == 200


@pytest.mark.asyncio
async def test_429_respects_retry_after() -> None:
    """429 with Retry-After header triggers wait then retry."""
    with aioresponses() as m:
        m.get(
            "http://example.com/api",
            status=429,
            headers={"Retry-After": "0.01"},
        )
        m.get("http://example.com/api", payload={"ok": True}, status=200)
        async with aiohttp.ClientSession() as session:
            resp = await retry_request(
                session, "GET", "http://example.com/api",
                max_retries=3, backoff_base=0.01,
            )
            assert resp.status == 200


@pytest.mark.asyncio
async def test_4xx_no_retry() -> None:
    """400 returned without retry."""
    with aioresponses() as m:
        m.get("http://example.com/api", status=400)
        async with aiohttp.ClientSession() as session:
            resp = await retry_request(
                session, "GET", "http://example.com/api",
                max_retries=3, backoff_base=0.01,
            )
            assert resp.status == 400
