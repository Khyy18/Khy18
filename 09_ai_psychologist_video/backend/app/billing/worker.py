import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text

from app.config import settings
from app.models.database import (
    async_session_factory,
    User,
    Session,
    Transaction,
    SessionStatus,
    TransactionType,
)

logger = logging.getLogger(__name__)


class BillingWorker:
    """
    Воркер биллинга: поддерживает per-session billing tasks и fallback watchdog.

    Per-session billing: для каждой активной сессии создается отдельная asyncio Task,
    которая каждые 60 секунд списывает rate с баланса пользователя через atomic SQL.

    Watchdog (_loop): сканирует активные сессии каждые 60 секунд и подхватывает те,
    для которых по какой-то причине не создан per-session task.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._redis = None
        self._session_tasks: dict[str, asyncio.Task] = {}

    async def _get_redis(self):
        """Получаем Redis-клиент (singleton)."""
        if self._redis is not None:
            return self._redis

        from app.redis_client import get_redis
        self._redis = await get_redis()
        return self._redis

    async def start(self):
        """Запуск фонового процесса биллинга."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("BillingWorker started")

    async def stop(self):
        """Остановка воркера."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Останавливаем все per-session tasks
        for session_id in list(self._session_tasks.keys()):
            await self.stop_session_billing(session_id)
        logger.info("BillingWorker stopped")

    async def start_session_billing(self, session_id: str, user_id: str, rate: Decimal):
        """
        Запускает per-session billing task.
        Task спит 60 секунд, затем в цикле списывает rate, проверяет баланс.
        """
        if session_id in self._session_tasks:
            return
        task = asyncio.create_task(
            self._session_billing_loop(session_id, user_id, rate)
        )
        self._session_tasks[session_id] = task
        logger.info(f"Started billing task for session {session_id}")

    async def stop_session_billing(self, session_id: str):
        """Останавливает per-session billing task."""
        task = self._session_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped billing task for session {session_id}")

    async def _session_billing_loop(self, session_id: str, user_id: str, rate: Decimal):
        """
        Per-session billing loop: sleep 60s, deduct rate atomically,
        check balance, publish warnings or force_end.
        """
        try:
            await asyncio.sleep(60)
            while True:
                new_balance = await self._deduct_balance(session_id, user_id, rate)
                if new_balance is None:
                    # Ошибка при списании, прекращаем
                    break

                if new_balance <= Decimal("0"):
                    await self._force_end_session(session_id)
                    break

                # Предупреждение о низком балансе
                remaining_minutes = new_balance / rate
                if remaining_minutes <= 2:
                    redis = await self._get_redis()
                    warning = json.dumps({
                        "type": "balance_warning",
                        "remaining_minutes": float(remaining_minutes),
                    })
                    await redis.publish(f"call:{session_id}", warning)

                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Session billing loop error for {session_id}: {e}")
        finally:
            self._session_tasks.pop(session_id, None)

    async def _deduct_balance(self, session_id: str, user_id: str, rate: Decimal) -> Decimal | None:
        """
        Atomic SQL deduction: UPDATE balance, SELECT new balance, create transaction.
        Returns new_balance or None on error.
        """
        try:
            async with async_session_factory() as session:
                # Atomic deduction
                await session.execute(
                    text("UPDATE users SET balance = balance - :rate WHERE id = :user_id"),
                    {"rate": float(rate), "user_id": user_id},
                )
                # Get new balance
                result = await session.execute(
                    text("SELECT balance FROM users WHERE id = :user_id"),
                    {"user_id": user_id},
                )
                row = result.fetchone()
                if row is None:
                    return None
                new_balance = Decimal(str(row[0]))

                # Update session total_cost
                await session.execute(
                    text(
                        "UPDATE sessions SET total_cost = total_cost + :rate WHERE id = :session_id"
                    ),
                    {"rate": float(rate), "session_id": session_id},
                )

                # Create debit transaction
                tx = Transaction(
                    user_id=user_id,
                    amount=rate,
                    type=TransactionType.debit,
                    source=f"session:{session_id}",
                )
                session.add(tx)
                await session.commit()
                return new_balance
        except Exception as e:
            logger.error(f"Deduct balance error for user {user_id}: {e}")
            return None

    async def _force_end_session(self, session_id: str):
        """Завершает сессию и шлет force_end через Redis pubsub."""
        try:
            async with async_session_factory() as session:
                await session.execute(
                    text(
                        "UPDATE sessions SET status = :status, ended_at = :ended_at "
                        "WHERE id = :session_id"
                    ),
                    {
                        "status": SessionStatus.finished.value,
                        "ended_at": datetime.utcnow().isoformat(),
                        "session_id": session_id,
                    },
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Force end session DB error: {e}")

        redis = await self._get_redis()
        await redis.publish(f"call:{session_id}", "force_end")
        logger.info(f"Session {session_id} force-ended: balance depleted")

    async def _loop(self):
        """
        Fallback watchdog: каждые 60 секунд проверяет активные сессии
        и запускает billing task для тех, у которых нет активного task.
        """
        while self._running:
            try:
                await self._process_orphaned_sessions()
            except Exception as e:
                logger.error(f"BillingWorker watchdog error: {e}")
            await asyncio.sleep(60)

    async def _process_orphaned_sessions(self):
        """
        Находит активные сессии без per-session billing task и запускает их.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(Session).where(Session.status == SessionStatus.active)
            )
            active_sessions = result.scalars().all()

            for active_session in active_sessions:
                if active_session.id not in self._session_tasks:
                    rate = active_session.rate_per_minute or settings.RATE_PER_MINUTE
                    await self.start_session_billing(
                        active_session.id, active_session.user_id, rate
                    )
