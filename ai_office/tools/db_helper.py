"""Вспомогательный модуль для синхронного доступа к БД из инструментов LangChain."""

import asyncio
from typing import Any, Coroutine


def run_async(coro: Coroutine) -> Any:
    """Запустить асинхронную корутину из синхронного контекста.

    Используется в LangChain tools, которые выполняются синхронно,
    но требуют доступа к async БД.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Если event loop уже запущен (внутри LangGraph), создаем новый поток
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
