"""Тесты реестра агентов AI Office."""

import pytest


def test_all_agents_registered():
    """Тест: все 8 агентов зарегистрированы."""
    from ai_office.agents import registry

    names = registry.get_names()
    assert len(names) == 8
    assert "alice" in names
    assert "sam" in names
    assert "max" in names
    assert "eva" in names
    assert "leo" in names
    assert "nova" in names
    assert "iris" in names
    assert "oscar" in names


def test_registry_get_case_insensitive():
    """Тест: поиск агента по имени без учёта регистра."""
    from ai_office.agents import registry

    assert registry.get("Alice") is not None
    assert registry.get("ALICE") is not None
    assert registry.get("alice") is not None
    assert registry.get("Sam") is not None
    assert registry.get("MAX") is not None
    assert registry.get("eva") is not None
    assert registry.get("Leo") is not None
    assert registry.get("NOVA") is not None
    assert registry.get("Iris") is not None
    assert registry.get("Oscar") is not None


def test_registry_get_unknown_returns_none():
    """Тест: поиск несуществующего агента возвращает None."""
    from ai_office.agents import registry

    assert registry.get("unknown_agent") is None
    assert registry.get("") is None


def test_registry_get_all():
    """Тест: get_all возвращает список всех конфигов."""
    from ai_office.agents import registry

    all_configs = registry.get_all()
    assert len(all_configs) == 8
    names = [c.name for c in all_configs]
    assert "alice" in names
    assert "sam" in names
    assert "max" in names
    assert "eva" in names
    assert "leo" in names
    assert "nova" in names
    assert "iris" in names
    assert "oscar" in names


def test_each_agent_has_tools_and_prompt():
    """Тест: каждый агент имеет инструменты и системный промпт."""
    from ai_office.agents import registry

    for config in registry.get_all():
        assert len(config.tools) > 0, f"Агент {config.name} не имеет инструментов"
        assert len(config.system_prompt) > 0, f"Агент {config.name} не имеет системного промпта"
        assert config.role, f"Агент {config.name} не имеет роли"


def test_each_new_agent_has_at_least_3_specialized_tools():
    """Тест: каждый новый агент имеет как минимум 3 специализированных инструмента."""
    from ai_office.agents import registry

    # Общие инструменты, не считаем как специализированные
    common_tool_names = {
        "create_task", "update_task_status", "assign_task",
        "get_active_tasks", "delegate_to_agent",
    }

    for name in ["max", "eva", "leo", "nova", "iris", "oscar"]:
        config = registry.get(name)
        assert config is not None
        specialized = [t for t in config.tools if t.name not in common_tool_names]
        assert len(specialized) >= 3, (
            f"Агент {name} имеет только {len(specialized)} специализированных инструментов"
        )


def test_agent_system_prompts_in_russian():
    """Тест: системные промпты содержат русский текст."""
    from ai_office.agents import registry

    for config in registry.get_all():
        # Проверяем наличие кириллицы в промпте
        has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in config.system_prompt)
        assert has_cyrillic, f"Промпт агента {config.name} не содержит русского текста"


def test_delegate_tool_in_all_agents():
    """Тест: все агенты имеют инструмент делегирования."""
    from ai_office.agents import registry

    for config in registry.get_all():
        tool_names = [t.name for t in config.tools]
        assert "delegate_to_agent" in tool_names, (
            f"Агент {config.name} не имеет инструмента delegate_to_agent"
        )
