"""Тесты асинхронных инструментов."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_office.tools.task_tools import create_task, get_active_tasks, update_task_status
from ai_office.tools.code_tools import execute_code, review_code, search_docs


@pytest.mark.asyncio
async def test_execute_code_async():
    """Тест: execute_code может быть вызван асинхронно."""
    with patch("ai_office.tools.code_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # Agent не найден - просто логирование пропускается
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await execute_code.ainvoke({"code": "print('hello')", "language": "python"})
        assert "python" in result
        assert "выполнен успешно" in result


@pytest.mark.asyncio
async def test_review_code_async():
    """Тест: review_code может быть вызван асинхронно."""
    with patch("ai_office.tools.code_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await review_code.ainvoke({"code": "x = 1", "context": "test"})
        assert "проверен" in result


@pytest.mark.asyncio
async def test_search_docs_async():
    """Тест: search_docs может быть вызван асинхронно."""
    with patch("ai_office.tools.code_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await search_docs.ainvoke({"query": "asyncio", "source": "docs"})
        assert "asyncio" in result
        assert "docs" in result


@pytest.mark.asyncio
async def test_get_active_tasks_async():
    """Тест: get_active_tasks может быть вызван асинхронно."""
    with patch("ai_office.tools.task_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_active_tasks.ainvoke({})
        assert "пока нет задач" in result


@pytest.mark.asyncio
async def test_update_task_status_not_found():
    """Тест: update_task_status возвращает ошибку если задача не найдена."""
    with patch("ai_office.tools.task_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await update_task_status.ainvoke({"task_id": 999, "new_status": "done"})
        assert "не найдена" in result


@pytest.mark.asyncio
async def test_create_task_async():
    """Тест: create_task может быть вызван асинхронно."""
    with patch("ai_office.tools.task_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock для поиска агента-исполнителя (не найден)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        result = await create_task.ainvoke({
            "description": "Тестовая задача",
            "priority": "high",
            "executor_name": "",
        })
        assert "Задача создана" in result
        assert "Тестовая задача" in result
        assert "high" in result
