"""Billing manager with Redis pub/sub decoupled from WebSocket.

Billing worker publishes events to channel `billing:{session_id}`.
The WebSocket handler subscribes and forwards events to the client.
Billing state is stored in Redis sorted set `billing_active` for scheduling.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

from app.config import settings
from app.models import BillingEvent, CallStatus

logger = logging.getLogger(__name__)


class BillingManager:
    """Manages user balances and per-minute billing via Redis pub/sub.

    Decoupled from WebSocket - publishes billing events to Redis channels.
    A separate subscriber (the WS handler) forwards events to clients.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._active_sessions: dict[str, asyncio.Task] = {}
        self._scheduler_task: Optional[asyncio.Task] = None

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

    async def publish_billing_event(self, session_id: str, event: BillingEvent) -> None:
        """Publish a billing event to the Redis pub/sub channel."""
        if self._redis is None:
            return
        channel = f"billing:{session_id}"
        await self._redis.publish(channel, event.model_dump_json())

    async def _persist_event(self, event: BillingEvent) -> None:
        """Persist billing event to PostgreSQL for audit trail."""
        try:
            from app.database import _async_session, BillingEventLog

            if _async_session is None:
                return  # Database not configured
            async with _async_session() as session:
                log_entry = BillingEventLog(
                    session_id=event.session_id,
                    user_id=event.user_id,
                    event_type=event.event_type,
                    amount=event.amount,
                    balance_after=event.balance_after,
                    timestamp=event.timestamp,
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist billing event: {e}")

    async def subscribe_billing_events(self, session_id: str):
        """Subscribe to billing events for a session.

        Returns a Redis pubsub object that can be iterated for messages.
        """
        if self._redis is None:
            return None
        pubsub = self._redis.pubsub()
        channel = f"billing:{session_id}"
        await pubsub.subscribe(channel)
        return pubsub

    async def start_billing_loop(
        self, session_id: str, user_id: str, ws=None
    ) -> None:
        """Start a background billing loop that deducts per minute.

        Publishes BALANCE_UPDATE events via Redis pub/sub.
        Publishes LOW_BALANCE_WARNING before balance runs out.
        Publishes TERMINATE_CALL when balance reaches zero.

        The ws parameter is optional for backward compatibility.
        If provided, events are also sent directly to the WebSocket.
        """
        task = asyncio.create_task(
            self._billing_worker(session_id, user_id, ws)
        )
        self._active_sessions[session_id] = task

        # Register in billing_active sorted set for scheduler
        if self._redis:
            next_tick = time.time() + settings.billing_interval_seconds
            await self._redis.zadd("billing_active", {session_id: next_tick})

    async def stop_billing_loop(self, session_id: str) -> None:
        """Stop the billing loop for a session."""
        task = self._active_sessions.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Remove from billing_active sorted set
        if self._redis:
            await self._redis.zrem("billing_active", session_id)

    def _calculate_remaining_time(self, balance: int, cost_per_interval: int) -> float:
        """Calculate remaining time in seconds before balance runs out."""
        if cost_per_interval <= 0:
            return float("inf")
        intervals_remaining = balance / cost_per_interval
        return intervals_remaining * settings.billing_interval_seconds

    async def _billing_worker(
        self, session_id: str, user_id: str, ws=None
    ) -> None:
        """Background worker that deducts balance every billing interval.

        Publishes events via Redis pub/sub. Optionally sends to WebSocket.
        """
        cost = settings.minute_cost_coins
        interval = settings.billing_interval_seconds
        grace_period = settings.grace_period_seconds
        low_balance_warned = False

        try:
            while True:
                await asyncio.sleep(interval)

                # Check if LOW_BALANCE_WARNING should be sent
                current_balance = await self.get_balance(user_id)
                remaining_time = self._calculate_remaining_time(current_balance, cost)

                if (
                    not low_balance_warned
                    and remaining_time <= grace_period
                    and current_balance > 0
                ):
                    low_balance_warned = True
                    warning_event = BillingEvent(
                        event_type="LOW_BALANCE_WARNING",
                        user_id=user_id,
                        session_id=session_id,
                        amount=0,
                        balance_after=current_balance,
                        timestamp=datetime.utcnow(),
                    )
                    await self.publish_billing_event(session_id, warning_event)
                    await self._persist_event(warning_event)
                    if ws:
                        try:
                            await ws.send_json(warning_event.model_dump(mode="json"))
                        except Exception:
                            pass

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
                    await self.publish_billing_event(session_id, event)
                    await self._persist_event(event)
                    if ws:
                        try:
                            await ws.send_json(event.model_dump(mode="json"))
                        except Exception:
                            logger.warning(
                                f"Failed to send billing update for session {session_id}"
                            )
                            break

                    # Update sorted set with next tick time
                    if self._redis:
                        next_tick = time.time() + interval
                        await self._redis.zadd(
                            "billing_active", {session_id: next_tick}
                        )

                    # Re-check remaining time after deduction for warning
                    remaining_time = self._calculate_remaining_time(remaining, cost)
                    if (
                        not low_balance_warned
                        and remaining_time <= grace_period
                        and remaining > 0
                    ):
                        low_balance_warned = True
                        warning_event = BillingEvent(
                            event_type="LOW_BALANCE_WARNING",
                            user_id=user_id,
                            session_id=session_id,
                            amount=0,
                            balance_after=remaining,
                            timestamp=datetime.utcnow(),
                        )
                        await self.publish_billing_event(session_id, warning_event)
                        await self._persist_event(warning_event)
                        if ws:
                            try:
                                await ws.send_json(
                                    warning_event.model_dump(mode="json")
                                )
                            except Exception:
                                pass
                else:
                    terminate_event = BillingEvent(
                        event_type="TERMINATE_CALL",
                        user_id=user_id,
                        session_id=session_id,
                        amount=0,
                        balance_after=remaining,
                        timestamp=datetime.utcnow(),
                    )
                    await self.publish_billing_event(session_id, terminate_event)
                    await self._persist_event(terminate_event)
                    if ws:
                        try:
                            await ws.send_json(
                                terminate_event.model_dump(mode="json")
                            )
                        except Exception:
                            logger.warning(
                                f"Failed to send terminate for session {session_id}"
                            )
                    break

        except asyncio.CancelledError:
            logger.info(f"Billing loop cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Billing worker error for session {session_id}: {e}")
        finally:
            # Cleanup from sorted set
            if self._redis:
                await self._redis.zrem("billing_active", session_id)

    async def start_scheduler(self) -> None:
        """Start the background billing scheduler.

        Periodically checks the billing_active sorted set for due ticks.
        This allows any pod to pick up billing work.
        """
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop_scheduler(self) -> None:
        """Stop the billing scheduler."""
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    async def _scheduler_loop(self) -> None:
        """Background loop that checks for due billing ticks and recovers orphaned sessions.

        If a billing worker dies (pod crash, unhandled exception), the session remains
        in billing_active but no worker is processing it. This scheduler detects such
        orphaned sessions (overdue by more than 2 intervals) and restarts their workers.
        """
        try:
            while True:
                await asyncio.sleep(5)  # Check every 5 seconds
                if self._redis is None:
                    continue

                now = time.time()
                # Get sessions with next_tick <= now (overdue)
                due_sessions = await self._redis.zrangebyscore(
                    "billing_active", 0, now
                )

                if not due_sessions:
                    continue

                # Check which overdue sessions are orphaned (not running locally)
                for session_id in due_sessions:
                    if session_id in self._active_sessions:
                        # Worker exists locally, skip
                        continue

                    # Check how overdue this session is
                    score = await self._redis.zscore("billing_active", session_id)
                    if score is None:
                        continue

                    overdue_seconds = now - score
                    # Only recover if overdue by more than 2 billing intervals
                    if overdue_seconds < settings.billing_interval_seconds * 2:
                        continue

                    # Try to recover: look up session data from Redis
                    session_data = await self._redis.get(f"session:{session_id}")
                    if not session_data:
                        # No session data, remove orphaned entry
                        await self._redis.zrem("billing_active", session_id)
                        logger.warning(
                            f"Removed orphaned billing entry with no session data: {session_id}"
                        )
                        continue

                    try:
                        session_info = json.loads(session_data)
                        user_id = session_info.get("user_id", "")
                        if user_id:
                            logger.info(
                                f"Recovering orphaned billing session: {session_id} "
                                f"(overdue {overdue_seconds:.0f}s)"
                            )
                            task = asyncio.create_task(
                                self._billing_worker(session_id, user_id, None)
                            )
                            self._active_sessions[session_id] = task
                        else:
                            await self._redis.zrem("billing_active", session_id)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Failed to recover session {session_id}: {e}")
                        await self._redis.zrem("billing_active", session_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Billing scheduler error: {e}")

    def get_active_session_count(self) -> int:
        """Get the number of active billing sessions on this instance."""
        return len(self._active_sessions)


billing_manager = BillingManager()
