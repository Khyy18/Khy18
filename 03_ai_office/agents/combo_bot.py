"""Конфигурация агента Combo Bot - интеграция с Telegram ботом Combo."""

from ai_office.agents.base import AgentConfig
from ai_office.tools.combo_bot_tools import get_bot_status, get_active_users, get_command_stats
from ai_office.tools.delegation import delegate_to_agent

COMBO_BOT_SYSTEM_PROMPT = """Ты - агент Combo Bot, мост между AI Office и Telegram ботом Combo.

Твои обязанности:
- Отчёт о статусе бота (uptime, активные пользователи)
- Мониторинг использования команд и нагрузки
- Предоставление статистики по активным пользователям
- Алерты о проблемах с ботом и высокой нагрузке

Правила:
- Всегда отвечай на русском языке
- Предоставляй краткую сводку при запросе статуса
- При проблемах с подключением к сервису - сообщай об этом явно
"""

# Конфигурация агента Combo Bot
combo_bot_config = AgentConfig(
    name="combo_bot",
    role="Combo Bot Integration",
    system_prompt=COMBO_BOT_SYSTEM_PROMPT,
    tools=[get_bot_status, get_active_users, get_command_stats, delegate_to_agent],
)
