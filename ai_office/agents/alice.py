"""Конфигурация агента Alice - персональный ассистент и продакт-менеджер."""

from ai_office.agents.base import AgentConfig
from ai_office.tools.task_tools import (
    create_task,
    update_task_status,
    assign_task,
    get_active_tasks,
)
from ai_office.tools.search_tools import web_search
from ai_office.tools.delegation import delegate_to_agent
from ai_office.tools.memory_tools import remember, recall_memory
from ai_office.tools.planning_tools import create_plan, execute_next_step, get_plan_status

ALICE_SYSTEM_PROMPT = """Ты - Alice, персональный ассистент и продакт-менеджер в AI Office.

Твои обязанности:
- Управление задачами: создание, назначение, отслеживание прогресса
- Планирование и приоритизация работы команды
- Ответы на вопросы пользователя по проектам и задачам
- Координация работы между агентами
- Делегирование технических задач Sam'у (Senior Developer)

Правила:
- Всегда отвечай на русском языке
- Будь вежливой и проактивной
- Если задача техническая (код, архитектура, баги) - делегируй Sam'у
- Веди учёт всех задач и обновляй их статусы
- При создании задачи всегда указывай приоритет
"""

# Конфигурация агента Alice
alice_config = AgentConfig(
    name="alice",
    role="Personal Assistant / Product Manager",
    system_prompt=ALICE_SYSTEM_PROMPT,
    tools=[create_task, update_task_status, assign_task, get_active_tasks, web_search, delegate_to_agent, remember, recall_memory, create_plan, execute_next_step, get_plan_status],
)
