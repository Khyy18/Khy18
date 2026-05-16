"""Инструмент делегирования задач между агентами."""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy import select

from ai_office.core.config import settings
from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent, Task


# Системные промпты агентов для вызова при делегировании
_AGENT_PROMPTS = {
    "alice": (
        "Ты - Alice, персональный ассистент и продакт-менеджер. "
        "Отвечай на русском языке. Будь краткой и по делу."
    ),
    "sam": (
        "Ты - Sam, Senior Developer. "
        "Отвечай на русском языке. Давай конкретные технические решения."
    ),
}


@tool
async def delegate_to_agent(agent_name: str, task_description: str) -> str:
    """Делегировать задачу другому агенту.

    Args:
        agent_name: Имя агента-исполнителя (alice или sam)
        task_description: Описание задачи для делегирования

    Returns:
        Ответ агента-исполнителя
    """
    agent_name_lower = agent_name.lower()

    if agent_name_lower not in _AGENT_PROMPTS:
        return f"Агент '{agent_name}' не найден. Доступные агенты: alice, sam."

    # Создаем задачу в БД
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name.ilike(agent_name_lower))
        )
        agent = result.scalar_one_or_none()

        executor_id = agent.id if agent else None

        task = Task(
            description=task_description,
            creator_type="agent",
            creator_id="delegation",
            executor_id=executor_id,
            status="in_progress",
            priority="medium",
        )
        session.add(task)
        await session.flush()

        # Логируем делегирование
        if agent:
            log = ActivityLog(
                agent_id=agent.id,
                action_type="task_delegated",
                action_description=f"Делегирована задача: {task_description}",
            )
            session.add(log)

        await session.commit()

    # Вызываем LLM от имени целевого агента
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
    )

    system_prompt = _AGENT_PROMPTS[agent_name_lower]
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=task_description),
    ]

    response = await llm.ainvoke(messages)
    return response.content
