"""Retry utility with exponential backoff for async operations."""

from __future__ import annotations

import asyncio


async def retry_async(coro_factory, max_retries: int = 3, base_delay: float = 1.0, label: str = ""):
    """Retry with exponential backoff.

    Args:
        coro_factory: Callable that returns an awaitable (called on each attempt).
        max_retries: Maximum number of attempts.
        base_delay: Base delay in seconds (doubled each retry).
        label: Label for logging.

    Returns:
        Result of coro_factory() on success, None on exhausted retries.
    """
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as exc:
            if attempt == max_retries - 1:
                print(f"[RETRY] {label} failed after {max_retries} attempts: {exc}")
                return None
            delay = base_delay * (2 ** attempt)
            print(f"[RETRY] {label} attempt {attempt+1} failed: {exc}, retry in {delay}s")
            await asyncio.sleep(delay)
    return None
