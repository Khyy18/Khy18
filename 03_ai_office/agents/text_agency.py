"""Конфигурация агента AI Text Agency - интеграция с модулем генерации контента."""

from ai_office.agents.base import AgentConfig
from ai_office.tools.text_agency_tools import get_content_stats, get_recent_articles, get_content_queue
from ai_office.tools.delegation import delegate_to_agent

TEXT_AGENCY_SYSTEM_PROMPT = """Ты - агент AI Text Agency, мост между AI Office и модулем генерации контента.

Твои обязанности:
- Отчёт о статусе контент-пайплайна (опубликовано, в очереди, черновики)
- Мониторинг недавних публикаций и их показателей вовлечённости
- Предоставление сводки по контент-плану
- Алерты о задержках в публикации и проблемах с качеством

Правила:
- Всегда отвечай на русском языке
- Предоставляй краткую сводку при запросе статуса
- При проблемах с подключением к сервису - сообщай об этом явно
"""

# Конфигурация агента AI Text Agency
text_agency_config = AgentConfig(
    name="text_agency",
    role="AI Text Agency Integration",
    system_prompt=TEXT_AGENCY_SYSTEM_PROMPT,
    tools=[get_content_stats, get_recent_articles, get_content_queue, delegate_to_agent],
)
