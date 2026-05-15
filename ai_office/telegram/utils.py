"""Утилиты для форматирования сообщений и парсинга упоминаний."""

import re
from typing import List

# Эмодзи для агентов
AGENT_EMOJIS: dict[str, str] = {
    "Alice": "\U0001f469\u200d\U0001f4bc",  # 👩‍💼
    "Sam": "\U0001f468\u200d\U0001f4bb",    # 👨‍💻
}


def format_agent_message(agent_name: str, role: str, text: str) -> str:
    """Форматирование сообщения от агента с именем, ролью и эмодзи.

    Args:
        agent_name: Имя агента
        role: Роль агента
        text: Текст сообщения

    Returns:
        Отформатированная строка
    """
    emoji = AGENT_EMOJIS.get(agent_name, "\U0001f916")  # 🤖 по умолчанию
    return f"{emoji} **{agent_name}** ({role}):\n{text}"


def parse_mentions(text: str) -> List[str]:
    """Парсинг упоминаний агентов из текста.

    Ищет паттерны вида @AgentName в тексте.

    Args:
        text: Входной текст сообщения

    Returns:
        Список имен упомянутых агентов
    """
    pattern = r"@(\w+)"
    mentions = re.findall(pattern, text)
    # Фильтруем только известных агентов (регистронезависимо)
    known_agents = {name.lower(): name for name in AGENT_EMOJIS.keys()}
    result = []
    for mention in mentions:
        lower_mention = mention.lower()
        if lower_mention in known_agents:
            result.append(known_agents[lower_mention])
    return result
