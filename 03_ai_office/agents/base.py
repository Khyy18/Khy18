"""Базовая конфигурация агента."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentConfig:
    """Конфигурация агента: имя, роль, системный промпт, инструменты."""

    name: str
    role: str
    system_prompt: str
    tools: list[Any] = field(default_factory=list)
    model: str = "gpt-4o-mini"
