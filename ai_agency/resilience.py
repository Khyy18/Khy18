"""Отказоустойчивость: retry с backoff, circuit breaker, graceful shutdown."""

import asyncio
import functools
import logging
import signal
import time
from enum import Enum
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Состояния circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit Breaker: защита от каскадных сбоев.

    Если 5 последовательных ошибок - открывает цепь на cooldown_seconds.
    После cooldown переходит в half_open (пропускает 1 запрос).
    Если запрос успешен - закрывает цепь. Если нет - открывает снова.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.name = name
        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Текущее состояние circuit breaker."""
        if self._state == CircuitState.OPEN:
            # Проверяем, прошёл ли cooldown
            if time.time() - self._last_failure_time >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("CircuitBreaker[%s]: OPEN -> HALF_OPEN", self.name)
        return self._state

    def record_success(self) -> None:
        """Записать успешный вызов."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("CircuitBreaker[%s]: HALF_OPEN -> CLOSED", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self) -> None:
        """Записать неудачный вызов."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "CircuitBreaker[%s]: CLOSED -> OPEN (failures=%d)",
                self.name,
                self._failure_count,
            )

    def can_execute(self) -> bool:
        """Проверить, можно ли выполнить запрос."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True
        return False


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
):
    """
    Декоратор для retry с экспоненциальным backoff.

    Повторяет вызов до max_retries раз с задержкой base_delay * 2^attempt,
    но не более max_delay секунд.
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            "Retry %s: попытка %d/%d, ожидание %.1f сек. Ошибка: %s",
                            func.__name__,
                            attempt + 1,
                            max_retries,
                            delay,
                            str(e),
                        )
                        await asyncio.sleep(delay)
            raise last_exception

        return wrapper

    return decorator


class GracefulShutdown:
    """
    Graceful shutdown: ожидает завершения текущих заказов перед выходом.

    Регистрирует обработчики SIGTERM/SIGINT.
    При получении сигнала устанавливает shutdown_event.
    """

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self._in_progress: int = 0

    def register_signals(self) -> None:
        """Зарегистрировать обработчики сигналов."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal)
        logger.info("GracefulShutdown: обработчики сигналов зарегистрированы")

    def _handle_signal(self) -> None:
        """Обработчик сигнала завершения."""
        logger.info(
            "GracefulShutdown: получен сигнал завершения, ожидание %d задач",
            self._in_progress,
        )
        self.shutdown_event.set()

    def task_started(self) -> None:
        """Отметить начало обработки задачи."""
        self._in_progress += 1

    def task_finished(self) -> None:
        """Отметить завершение обработки задачи."""
        self._in_progress -= 1

    async def wait_for_completion(self, timeout: float = 30.0) -> None:
        """Дождаться завершения всех текущих задач или таймаута."""
        start = time.time()
        while self._in_progress > 0:
            if time.time() - start > timeout:
                logger.warning(
                    "GracefulShutdown: таймаут, %d задач не завершены",
                    self._in_progress,
                )
                break
            await asyncio.sleep(0.5)
        logger.info("GracefulShutdown: все задачи завершены")


async def recover_stale_orders() -> int:
    """
    Восстановление зависших заказов при старте.

    Находит заказы со статусом 'processing' и возвращает их в 'pending'.
    Возвращает количество восстановленных заказов.
    """
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE orders SET status = 'pending' WHERE status = 'processing'"
        )
        count = cursor.rowcount
        await db.commit()

    if count > 0:
        logger.info("Восстановлено %d зависших заказов", count)
    return count
