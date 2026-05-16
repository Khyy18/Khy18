"""Инструменты памяти агентов - сохранение и поиск фактов/решений."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.memory import agent_memory
from ai_office.core.models import ActivityLog, Agent

# Текущий агент (устанавливается оркестратором перед вызовом инструментов)
_current_agent: str = "alice"


def set_current_agent(name: str) -> None:
    """Установить имя текущего агента для контекста инструментов."""
    global _current_agent
    _current_agent = name


def get_current_agent() -> str:
    """Получить имя текущего агента."""
    return _current_agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени текущего агента."""
    agent_name = get_current_agent()
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.name.ilike(agent_name))
            )
            agent = result.scalar_one_or_none()
            if agent:
                log = ActivityLog(
                    agent_id=agent.id,
                    action_type=action_type,
                    action_description=description,
                )
                session.add(log)
                await session.commit()
    except Exception:
        pass


@tool
async def remember(fact: str) -> str:
    """Сохранить важный факт или решение в долгосрочную память.

    Args:
        fact: Факт или решение для запоминания

    Returns:
        Подтверждение сохранения
    """
    agent_name = get_current_agent()
    memory_id = agent_memory.store(
        agent_name=agent_name,
        text=fact,
        metadata={"type": "manual", "agent": agent_name},
    )

    if memory_id:
        await _log_activity("memory_stored", f"Сохранено в память: {fact[:100]}")
        return f"Запомнено (id: {memory_id}): {fact[:100]}"
    else:
        return "Не удалось сохранить в память. Сервис памяти недоступен."


@tool
async def recall_memory(query: str) -> str:
    """Вспомнить релевантную информацию из долгосрочной памяти.

    Args:
        query: Запрос для поиска в памяти

    Returns:
        Найденные воспоминания или сообщение об отсутствии результатов
    """
    agent_name = get_current_agent()
    memories = agent_memory.recall(agent_name=agent_name, query=query, k=5)

    if not memories:
        await _log_activity("memory_recall", f"Поиск в памяти (нет результатов): {query[:100]}")
        return "В памяти ничего не найдено по данному запросу."

    lines = []
    for m in memories:
        lines.append(f"- {m['text']}")

    await _log_activity("memory_recall", f"Поиск в памяти ({len(memories)} результатов): {query[:100]}")
    return "Найдено в памяти:\n" + "\n".join(lines)
