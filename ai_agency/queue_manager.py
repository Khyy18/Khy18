"""Менеджер очереди заказов на основе asyncio.PriorityQueue."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict

import config

logger = logging.getLogger(__name__)


@dataclass(order=True)
class QueueItem:
    """Элемент очереди с приоритетом (меньше = выше приоритет)."""

    priority: int
    order_id: int = field(compare=False)
    service_type: str = field(compare=False)
    input_text: str = field(compare=False)
    enqueued_at: float = field(compare=False, default_factory=time.time)


class OrderQueue:
    """
    Очередь обработки заказов с пулом воркеров.

    Приоритеты: 0 = urgent, 1 = normal, 2 = low.
    Воркеры берут заказы из очереди и обрабатывают через pipeline.
    """

    def __init__(
        self,
        max_size: Optional[int] = None,
        worker_count: Optional[int] = None,
    ):
        self._max_size = max_size or config.QUEUE_MAX_SIZE
        self._worker_count = worker_count or config.QUEUE_WORKERS
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=self._max_size
        )
        self._workers: list = []
        self._active_workers: int = 0
        self._total_processed: int = 0
        self._total_processing_time: float = 0.0
        self._running: bool = False

    async def start(self) -> None:
        """Запустить пул воркеров."""
        if self._running:
            return
        self._running = True
        for i in range(self._worker_count):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info(
            "Очередь запущена: max_size=%d, workers=%d",
            self._max_size,
            self._worker_count,
        )

    async def stop(self) -> None:
        """Остановить воркеры (ждёт завершения текущих задач)."""
        self._running = False
        # Отменяем воркеры
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Очередь остановлена")

    async def enqueue_order(
        self,
        order_id: int,
        service_type: str,
        input_text: str,
        priority: int = 1,
    ) -> Optional[float]:
        """
        Добавить заказ в очередь.

        Возвращает None если успешно, или ожидаемое время ожидания если очередь полна.
        """
        if self._queue.full():
            estimated_wait = self._get_estimated_wait()
            logger.warning(
                "Очередь полна (size=%d), order_id=%d отклонён. Ожидание ~%.1f сек",
                self._queue.qsize(),
                order_id,
                estimated_wait,
            )
            return estimated_wait

        item = QueueItem(
            priority=priority,
            order_id=order_id,
            service_type=service_type,
            input_text=input_text,
        )
        await self._queue.put(item)
        logger.info(
            "Заказ #%d добавлен в очередь (priority=%d, size=%d)",
            order_id,
            priority,
            self._queue.qsize(),
        )
        return None

    def get_queue_stats(self) -> Dict:
        """Получить статистику очереди."""
        avg_time = (
            self._total_processing_time / self._total_processed
            if self._total_processed > 0
            else 0.0
        )
        return {
            "queue_size": self._queue.qsize(),
            "active_workers": self._active_workers,
            "avg_processing_time": round(avg_time, 2),
            "total_processed": self._total_processed,
            "max_size": self._max_size,
            "worker_count": self._worker_count,
        }

    def _get_estimated_wait(self) -> float:
        """Рассчитать ожидаемое время ожидания."""
        if self._total_processed == 0:
            return 60.0  # дефолт 60 секунд
        avg_time = self._total_processing_time / self._total_processed
        queue_size = self._queue.qsize()
        workers = max(self._worker_count, 1)
        return (queue_size / workers) * avg_time

    async def _worker(self, worker_id: int) -> None:
        """Воркер, обрабатывающий заказы из очереди."""
        logger.debug("Воркер #%d запущен", worker_id)
        while self._running:
            try:
                item: QueueItem = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            self._active_workers += 1
            start_time = time.time()

            # Уведомляем GracefulShutdown о начале задачи
            _graceful_shutdown = None
            try:
                from resilience import GracefulShutdown
                import main_multi
                _graceful_shutdown = getattr(main_multi, '_graceful_shutdown', None)
            except (ImportError, AttributeError):
                pass
            if _graceful_shutdown:
                _graceful_shutdown.task_started()

            try:
                # Импорт pipeline здесь для избежания циклических импортов
                import pipeline
                from models import ServiceType

                service_type = ServiceType(item.service_type)
                result, variant_id = await pipeline.process_order(
                    service_type, item.input_text
                )

                import database

                if result:
                    await database.update_order_status(
                        item.order_id, "completed", result
                    )
                    logger.info("Заказ #%d обработан успешно", item.order_id)
                else:
                    await database.update_order_status(item.order_id, "failed")
                    logger.warning("Заказ #%d не удалось обработать", item.order_id)

            except Exception as e:
                logger.error(
                    "Ошибка обработки заказа #%d: %s", item.order_id, e
                )
            finally:
                elapsed = time.time() - start_time
                self._total_processing_time += elapsed
                self._total_processed += 1
                self._active_workers -= 1
                self._queue.task_done()
                # Уведомляем GracefulShutdown о завершении задачи
                if _graceful_shutdown:
                    _graceful_shutdown.task_finished()
