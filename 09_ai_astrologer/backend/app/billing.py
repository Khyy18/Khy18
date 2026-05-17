"""Billing manager for per-minute call deductions via Redis and WebSockets."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import WebSocket

from app.config import settings
from app.models import BillingEvent, CallStatus

logger = logging.getLogger(__name__)


class BillingManager:
    """Manages user balances and per-minute billing for call sessions."""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._active_sessions: dict[str, asyncio.Task] = {}

    @property
    def redis(self):
        return self._redis

    @redis.setter
    def redis(self, client):
        self._redis = client

    async def get_balance(self, user_id: str) -> int:
        """Get current balance for a user from Redis."""
        if self._redis is None:
            return 0
        balance = await self._redis.get(f"balance:{user_id}")
        if balance is None:
            return 0
        return int(balance)

    async def set_balance(self, user_id: str, amount: int) -> None:
        """Set user balance in Redis."""
        if self._redis is None:
            return
        await self._redis.set(f"balance:{user_id}", str(amount))

    # Lua script for atomic check-and-deduct
    _DEDUCT_SCRIPT = """
    local key = KEYS[1]
    local cost = tonumber(ARGV[1])
    local current = tonumber(redis.call('GET', key) or '0')
    if current < cost then
        return {0, current}
    end
    local new_balance = current - cost
    redis.call('SET', key, tostring(new_balance))
    return {1, new_balance}
    """

    async def deduct_minute(self, user_id: str, cost: int) -> tuple[bool, int]:
        """Deduct per-minute cost from user balance atomically.

        Uses a Lua script to prevent race conditions between
        concurrent deductions or top-ups.

        Returns (success, remaining_balance).
        If balance is insufficient, returns (False, current_balance).
        """
        if self._redis is None:
            return False, 0

        key = f"balance:{user_id}"
        result = await self._redis.eval(
            self._DEDUCT_SCRIPT, 1, key, str(cost)
        )
        success = bool(result[0])
        remaining = int(result[1])
        return success, remaining

    async def topup_balance(self, user_id: str, amount: int) -> int:
        """Add coins to user balance. Returns new balance."""
        current = await self.get_balance(user_id)
        new_balance = current + amount
        await self.set_balance(user_id, new_balance)
        return new_balance

    async def start_billing_loop(
        self, session_id: str, user_id: str, ws: WebSocket
    ) -> None:
        """Start a background billing loop that deducts per minute.

        Sends BALANCE_UPDATE messages every interval.
        Sends TERMINATE_CALL when balance reaches zero.
        """
        task = asyncio.create_task(
            self._billing_worker(session_id, user_id, ws)
        )
        self._active_sessions[session_id] = task

    async def stop_billing_loop(self, session_id: str) -> None:
        """Stop the billing loop for a session."""
        task = self._active_sessions.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _billing_worker(
        self, session_id: str, user_id: str, ws: WebSocket
    ) -> None:
        """Background worker that deducts balance every billing interval."""
        cost = settings.minute_cost_coins
        interval = settings.billing_interval_seconds

        try:
            while True:
                await asyncio.sleep(interval)

                success, remaining = await self.deduct_minute(user_id, cost)

                if success:
                    event = BillingEvent(
                        event_type="BALANCE_UPDATE",
                        user_id=user_id,
                        session_id=session_id,
                        amount=cost,
                        balance_after=remaining,
                        timestamp=datetime.utcnow(),
                    )
                    try:
                        await ws.send_json(event.model_dump(mode="json"))
                    except Exception:
                        logger.warning(
                            f"Failed to send billing update for session {session_id}"
                        )
                        break
                else:
                    terminate_event = BillingEvent(
                        event_type="TERMINATE_CALL",
                        user_id=user_id,
                        session_id=session_id,
                        amount=0,
                        balance_after=remaining,
                        timestamp=datetime.utcnow(),
                    )
                    try:
                        await ws.send_json(terminate_event.model_dump(mode="json"))
                    except Exception:
                        logger.warning(
                            f"Failed to send terminate for session {session_id}"
                        )
                    break

        except asyncio.CancelledError:
            logger.info(f"Billing loop cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Billing worker error for session {session_id}: {e}")


billing_manager = BillingManager()
