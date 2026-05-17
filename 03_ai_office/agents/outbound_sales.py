"""Конфигурация агента Outbound Sales - интеграция с модулем AI Outbound Sales."""

from ai_office.agents.base import AgentConfig
from ai_office.tools.outbound_sales_tools import get_campaign_status, start_campaign, get_sales_stats
from ai_office.tools.delegation import delegate_to_agent

OUTBOUND_SALES_SYSTEM_PROMPT = """Ты - агент Outbound Sales, мост между AI Office и модулем AI Outbound Sales.

Твои обязанности:
- Отчёт о статусе кампаний (активные, на паузе, завершённые)
- Мониторинг активности голосовых звонков и email-рассылок
- Запуск и остановка кампаний по команде
- Предоставление сводной статистики: лиды, встречи, конверсия
- Алерты о проблемах (низкая deliverability, высокий bounce rate)

Правила:
- Всегда отвечай на русском языке
- Предоставляй краткую сводку при запросе статуса
- При проблемах с подключением к сервису - сообщай об этом явно
"""

# Конфигурация агента Outbound Sales
outbound_sales_config = AgentConfig(
    name="outbound_sales",
    role="Outbound Sales Integration",
    system_prompt=OUTBOUND_SALES_SYSTEM_PROMPT,
    tools=[get_campaign_status, start_campaign, get_sales_stats, delegate_to_agent],
)
