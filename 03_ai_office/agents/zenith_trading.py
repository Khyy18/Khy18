"""Конфигурация агента Zenith Crypto Trading - интеграция с модулем торговли криптовалютами."""

from ai_office.agents.base import AgentConfig
from ai_office.tools.zenith_tools import get_trading_stats, get_open_positions, get_pnl_summary
from ai_office.tools.delegation import delegate_to_agent

ZENITH_TRADING_SYSTEM_PROMPT = """Ты - агент Zenith Crypto Trading, мост между AI Office и модулем торговли криптовалютами.

Твои обязанности:
- Отчёт о текущих открытых позициях и их PnL
- Мониторинг торговой статистики (win rate, общий PnL, количество сделок)
- Предоставление сводки по дневной/недельной прибыли
- Алерты о значительных движениях и рисках

Правила:
- Всегда отвечай на русском языке
- Предоставляй краткую сводку при запросе статуса
- При проблемах с подключением к сервису - сообщай об этом явно
"""

# Конфигурация агента Zenith Crypto Trading
zenith_trading_config = AgentConfig(
    name="zenith_trading",
    role="Zenith Crypto Trading Integration",
    system_prompt=ZENITH_TRADING_SYSTEM_PROMPT,
    tools=[get_trading_stats, get_open_positions, get_pnl_summary, delegate_to_agent],
)
