"""Супервизор задач арбитражного бота.

Управляет жизненным циклом asyncio-задач: мониторинг, автоматический
перезапуск при падениях (до 3 раз за 5 минут), оповещение при отказе.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

import aiohttp

from arbitrage import telegram_bot

logger = logging.getLogger(__name__)

# Лимиты перезапуска
_MAX_RESTARTS: int = 3
_RESTART_WINDOW_SEC: float = 300.0  # 5 минут


class TaskSupervisor:
    """Супервизор для asyncio-задач арбитражного бота.

    Запускает задачи, мониторит их состояние, перезапускает при падениях.
    Если все попытки перезапуска исчерпаны - логирует критическую ошибку
    и отправляет Telegram-алерт.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._restart_counts: dict[str, list[float]] = {}
        self._last_errors: dict[str, Optional[str]] = {}
        self._factories: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}

    async def run(
        self,
        task_factories: list[tuple[str, Callable[..., Coroutine[Any, Any, None]]]],
        state: dict,
        session: aiohttp.ClientSession,
    ) -> None:
        """Главный цикл супервизора.

        Args:
            task_factories: список (имя, async_factory_fn) кортежей.
                Каждая фабрика вызывается как factory(state, session).
            state: общее состояние бота.
            session: aiohttp-сессия для сетевых вызовов.
        """
        # Инициализация задач
        for name, factory in task_factories:
            self._factories[name] = factory
            self._restart_counts[name] = []
            self._last_errors[name] = None
            task = asyncio.create_task(factory(state, session), name=name)
            self._tasks[name] = task
            logger.info("[SUPERVISOR] Запущена задача: %s", name)

        # Цикл мониторинга
        while True:
            if not self._tasks:
                logger.warning("[SUPERVISOR] Нет активных задач, выход")
                break

            # Ждём завершения любой задачи
            done, _ = await asyncio.wait(
                list(self._tasks.values()),
                return_when=asyncio.FIRST_COMPLETED,
            )

            for completed_task in done:
                task_name = completed_task.get_name()

                # Если задача была отменена - не перезапускаем
                if completed_task.cancelled():
                    logger.warning(
                        "[SUPERVISOR] Задача '%s' была отменена", task_name
                    )
                    self._tasks.pop(task_name, None)
                    continue

                # Проверяем исключение
                exc = completed_task.exception()
                if exc is not None:
                    error_msg = f"{type(exc).__name__}: {exc}"
                    self._last_errors[task_name] = error_msg
                    logger.error(
                        "[SUPERVISOR] Задача '%s' упала: %s",
                        task_name,
                        error_msg,
                    )

                    # Проверяем лимит перезапусков
                    if self._can_restart(task_name):
                        await self._restart_task(task_name, state, session)
                    else:
                        # Все перезапуски исчерпаны
                        logger.critical(
                            "[SUPERVISOR] Задача '%s' исчерпала лимит перезапусков. "
                            "Последняя ошибка: %s",
                            task_name,
                            error_msg,
                        )
                        await self._send_critical_alert(
                            session, task_name, error_msg
                        )
                        self._tasks.pop(task_name, None)
                else:
                    # Задача завершилась без ошибки (нормально)
                    logger.info(
                        "[SUPERVISOR] Задача '%s' завершилась нормально",
                        task_name,
                    )
                    self._tasks.pop(task_name, None)

    def _can_restart(self, task_name: str) -> bool:
        """Проверяет, можно ли перезапустить задачу (макс 3 за 5 минут)."""
        now = time.time()
        timestamps = self._restart_counts.get(task_name, [])

        # Удаляем старые перезапуски (старше 5 минут)
        timestamps = [ts for ts in timestamps if now - ts < _RESTART_WINDOW_SEC]
        self._restart_counts[task_name] = timestamps

        return len(timestamps) < _MAX_RESTARTS

    async def _restart_task(
        self,
        task_name: str,
        state: dict,
        session: aiohttp.ClientSession,
    ) -> None:
        """Перезапускает упавшую задачу."""
        now = time.time()
        self._restart_counts[task_name].append(now)
        restart_num = len(self._restart_counts[task_name])

        logger.warning(
            "[SUPERVISOR] Перезапуск задачи '%s' (попытка %d/%d)",
            task_name,
            restart_num,
            _MAX_RESTARTS,
        )

        factory = self._factories[task_name]
        # Небольшая задержка перед перезапуском
        await asyncio.sleep(2.0)
        new_task = asyncio.create_task(factory(state, session), name=task_name)
        self._tasks[task_name] = new_task

    async def _send_critical_alert(
        self,
        session: aiohttp.ClientSession,
        task_name: str,
        error_msg: str,
    ) -> None:
        """Отправляет критический алерт в Telegram."""
        text = (
            f"<b>CRITICAL: Задача '{task_name}' мертва</b>\n\n"
            f"Исчерпаны все {_MAX_RESTARTS} перезапуска за "
            f"{int(_RESTART_WINDOW_SEC)}сек.\n"
            f"<pre>{error_msg[:500]}</pre>"
        )
        try:
            await telegram_bot.send_message(session, text)
        except Exception as e:
            logger.error(
                "[SUPERVISOR] Не удалось отправить алерт: %s", e
            )

    def get_health(self) -> dict[str, dict[str, Any]]:
        """Возвращает состояние здоровья всех задач.

        Returns:
            {task_name: {"status": "running"|"dead"|"restarting",
                         "restarts": int, "last_error": str|None}}
        """
        now = time.time()
        result: dict[str, dict[str, Any]] = {}

        for name in self._factories:
            task = self._tasks.get(name)
            timestamps = self._restart_counts.get(name, [])
            # Считаем перезапуски в окне
            recent_restarts = len(
                [ts for ts in timestamps if now - ts < _RESTART_WINDOW_SEC]
            )

            if task is None or task.done():
                status = "dead"
            elif recent_restarts > 0 and not task.done():
                status = "restarting"
            else:
                status = "running"

            result[name] = {
                "status": status,
                "restarts": recent_restarts,
                "last_error": self._last_errors.get(name),
            }

        return result
