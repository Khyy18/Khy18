"""Инструмент делегирования задач между агентами."""

import json
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.config import settings
from ai_office.core.database import async_session
from ai_office.core.llm_provider import llm_provider
from ai_office.core.models import ActivityLog, Agent, DelegationTrace, Task
from ai_office.core.rate_limiter import Priority


@tool
async def delegate_to_agent(agent_name: str, task_description: str) -> str:
    """Делегировать задачу другому агенту.

    Args:
        agent_name: Имя агента-исполнителя (alice, sam, max, eva, leo, nova)
        task_description: Описание задачи для делегирования

    Returns:
        Ответ агента-исполнителя
    """
    from ai_office.agents.registry import registry

    agent_name_lower = agent_name.lower()
    config = registry.get(agent_name_lower)

    if not config:
        available = ", ".join(registry.get_names())
        return f"Агент '{agent_name}' не найден. Доступные агенты: {available}."

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

    # Вызываем LLM от имени целевого агента с привязкой инструментов
    messages = [
        SystemMessage(content=config.system_prompt),
        HumanMessage(content=task_description),
    ]

    # Цикл выполнения инструментов (максимум 3 итерации)
    for _ in range(3):
        response = await llm_provider.ainvoke_with_retry(
            messages=messages,
            agent_name=agent_name_lower,
            tools=config.tools if config.tools else None,
            priority=Priority.NORMAL,
        )
        messages.append(response)

        if not response.tool_calls:
            break

        # Выполняем вызовы инструментов
        tool_map = {t.name: t for t in config.tools}
        for tool_call in response.tool_calls:
            if tool_call["name"] in tool_map:
                result = await tool_map[tool_call["name"]].ainvoke(tool_call["args"])
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )
            else:
                messages.append(
                    ToolMessage(
                        content=f"Инструмент '{tool_call['name']}' не найден.",
                        tool_call_id=tool_call["id"],
                    )
                )

    # Store delegation trace inside a try/except to avoid losing
    # observability if the trace commit fails after delegation completed.
    try:
        trace_messages = []
        for msg in messages:
            role = "system"
            if hasattr(msg, "type"):
                role = msg.type
            content = getattr(msg, "content", str(msg))
            trace_messages.append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            })

        async with async_session() as session:
            trace = DelegationTrace(
                source_agent="delegation",
                target_agent=agent_name_lower,
                task_id=task.id,
                messages_json=json.dumps(trace_messages, ensure_ascii=False),
            )
            session.add(trace)
            await session.commit()
    except Exception as e:
        # Log but don't crash - the delegation itself already succeeded
        import logging
        logging.getLogger(__name__).warning(
            f"Failed to store delegation trace: {e}"
        )

    return response.content
