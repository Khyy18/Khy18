"""Tests for utils/retry.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from utils.retry import retry_async


@pytest.mark.asyncio
async def test_retry_success_first_attempt():
    """Success on first attempt - no retries needed."""
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(factory, max_retries=3, base_delay=0.01, label="test")
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_success_after_failure():
    """Fails first, succeeds on second attempt."""
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient error")
        return "recovered"

    result = await retry_async(factory, max_retries=3, base_delay=0.01, label="test")
    assert result == "recovered"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_gives_up():
    """All attempts fail - returns None."""
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("persistent error")

    result = await retry_async(factory, max_retries=3, base_delay=0.01, label="test")
    assert result is None
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_respects_max_retries():
    """With max_retries=2, only 2 attempts."""
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    result = await retry_async(factory, max_retries=2, base_delay=0.01, label="test")
    assert result is None
    assert call_count == 2
