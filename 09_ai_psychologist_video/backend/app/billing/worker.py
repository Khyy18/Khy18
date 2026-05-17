import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update

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
    Воркер биллинга: каждые 60 секунд сканирует активные сессии,
    списывает стоимость за минуту с баланса пользователя,
    создает транзакцию типа debit.
    Если баланс <= 0, завершает сессию и отправляет force_end через Redis pubsub.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._redis = None

    async def _get_redis(self):
        """Получаем Redis-клиент. Использует shared module для корректной работы pubsub."""
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
        if self._redis:
            await self._redis.close()
        logger.info("BillingWorker stopped")

    async def _loop(self):
        """Основной цикл: каждые 60 секунд обрабатываем активные сессии."""
        while self._running:
            try:
                await self._process_active_sessions()
            except Exception as e:
                logger.error(f"BillingWorker error: {e}")
            await asyncio.sleep(60)

    async def _process_active_sessions(self):
        """
        Сканируем все активные сессии, для каждой:
        1. Списываем rate_per_minute с баланса пользователя
        2. Создаем транзакцию debit
        3. Если баланс <= 0, завершаем сессию и шлем force_end
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(Session).where(Session.status == SessionStatus.active)
            )
            active_sessions = result.scalars().all()

            for active_session in active_sessions:
                # Получаем пользователя
                user_result = await session.execute(
                    select(User).where(User.id == active_session.user_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    continue

                rate = active_session.rate_per_minute or settings.RATE_PER_MINUTE

                # Списываем с баланса
                new_balance = user.balance - rate
                user.balance = new_balance

                # Обновляем total_cost сессии
                active_session.total_cost = (active_session.total_cost or Decimal("0")) + rate

                # Создаем транзакцию списания
                tx = Transaction(
                    user_id=user.id,
                    amount=rate,
                    type=TransactionType.debit,
                    source=f"session:{active_session.id}",
                )
                session.add(tx)

                # Если баланс исчерпан - завершаем сессию
                if new_balance <= Decimal("0"):
                    active_session.status = SessionStatus.finished
                    active_session.ended_at = datetime.utcnow()

                    # Публикуем force_end через Redis pubsub
                    redis = await self._get_redis()
                    await redis.publish(
                        f"call:{active_session.id}",
                        "force_end"
                    )
                    logger.info(
                        f"Session {active_session.id} force-ended: balance depleted"
                    )

            await session.commit()
