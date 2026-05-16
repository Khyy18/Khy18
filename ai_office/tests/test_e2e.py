"""E2E интеграционные тесты AI Office.

Проверяют полный цикл: создание задач, активность, делегирование,
плагины, администрирование и мультитенантность.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import (
    Agent,
    ActivityLog,
    DelegationTrace,
    SystemSetting,
    Task,
    Workspace,
)


# --- Тест 1: Полный цикл создания и получения задачи ---


@pytest.mark.asyncio
async def test_full_flow_task_creation_and_retrieval(test_client: AsyncClient):
    """Проверяет полный цикл: создание задачи через POST и получение через GET.

    Убеждается, что задача создается со статусом 'open' и приоритетом 'high'.
    """
    # Создаем задачу через API
    response = await test_client.post(
        "/api/tasks",
        json={"description": "Тестовая задача", "priority": "high"},
    )
    assert response.status_code == 201
    task_data = response.json()
    assert task_data["description"] == "Тестовая задача"
    assert task_data["priority"] == "high"
    assert task_data["status"] == "open"
    task_id = task_data["id"]

    # Получаем список задач и проверяем, что новая задача в нем
    response = await test_client.get("/api/tasks")
    assert response.status_code == 200
    tasks = response.json()
    assert tasks["total"] >= 1

    # Ищем нашу задачу в списке
    found = False
    for item in tasks["items"]:
        if item["id"] == task_id:
            assert item["status"] == "open"
            assert item["priority"] == "high"
            assert item["description"] == "Тестовая задача"
            found = True
            break
    assert found, "Созданная задача не найдена в списке"


# --- Тест 2: Полный цикл с активностью и broadcast ---


@pytest.mark.asyncio
async def test_full_flow_with_activity_and_broadcast(
    async_session: AsyncSession, test_client: AsyncClient
):
    """Проверяет создание задачи с активностью агента и вызов broadcast_event.

    Создает агентов, задачу, лог активности и проверяет, что broadcast_event
    вызывается при создании задачи через API.
    """
    # Создаем агентов в БД
    alice = Agent(
        name="Alice_e2e",
        role="PM",
        system_prompt="Тестовый промпт Alice",
        status="idle",
    )
    sam = Agent(
        name="Sam_e2e",
        role="Dev",
        system_prompt="Тестовый промпт Sam",
        status="idle",
    )
    async_session.add_all([alice, sam])
    await async_session.flush()

    # Создаем задачу для Alice
    task = Task(
        description="E2E задача для Alice",
        creator_type="user",
        creator_id="test_user",
        executor_id=alice.id,
        status="open",
        priority="medium",
    )
    async_session.add(task)
    await async_session.flush()

    # Создаем запись активности
    log = ActivityLog(
        agent_id=alice.id,
        action_type="task_created",
        action_description="Создана E2E задача",
    )
    async_session.add(log)
    await async_session.commit()

    # Проверяем, что лог активности доступен через API
    response = await test_client.get("/api/activity")
    assert response.status_code == 200
    activity_data = response.json()
    assert activity_data["total"] >= 1

    found_log = False
    for item in activity_data["items"]:
        if item["action_description"] == "Создана E2E задача":
            assert item["agent_id"] == alice.id
            assert item["action_type"] == "task_created"
            found_log = True
            break
    assert found_log, "Лог активности не найден в ответе API"

    # Проверяем, что broadcast_event вызывается при создании задачи через API
    with patch(
        "ai_office.api.routes.tasks.broadcast_event", new_callable=AsyncMock
    ) as mock_broadcast:
        response = await test_client.post(
            "/api/tasks",
            json={"description": "Broadcast test задача", "priority": "low"},
        )
        assert response.status_code == 201
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        assert call_args[0][0] == "new_task"
        assert call_args[0][1]["description"] == "Broadcast test задача"


# --- Тест 3: Хранение DelegationTrace ---


@pytest.mark.asyncio
async def test_delegation_trace_storage(async_session: AsyncSession):
    """Проверяет создание и сохранение записи DelegationTrace в БД.

    Создает агентов Alice и Sam, затем трассировку делегирования
    и убеждается, что она корректно сохранена и извлекается из БД.
    """
    # Создаем агентов
    alice = Agent(
        name="Alice_trace",
        role="PM",
        system_prompt="Alice trace test",
        status="idle",
    )
    sam = Agent(
        name="Sam_trace",
        role="Dev",
        system_prompt="Sam trace test",
        status="idle",
    )
    async_session.add_all([alice, sam])
    await async_session.flush()

    # Создаем DelegationTrace
    messages = [{"role": "system", "content": "delegated"}]
    trace = DelegationTrace(
        source_agent="alice",
        target_agent="sam",
        messages_json=json.dumps(messages),
    )
    async_session.add(trace)
    await async_session.commit()

    # Проверяем, что запись доступна из БД
    result = await async_session.execute(
        select(DelegationTrace).where(DelegationTrace.source_agent == "alice")
    )
    saved_trace = result.scalar_one_or_none()
    assert saved_trace is not None
    assert saved_trace.source_agent == "alice"
    assert saved_trace.target_agent == "sam"
    assert json.loads(saved_trace.messages_json) == messages


# --- Тест 4: Система плагинов загружает researcher ---


@pytest.mark.asyncio
async def test_plugin_system_loads_researcher(test_client: AsyncClient):
    """Проверяет, что плагин 'researcher' загружается и доступен через API.

    Вызывает load_plugins() для инициализации, затем GET /api/plugins
    и проверяет наличие researcher с корректным display_name и инструментами.
    """
    from ai_office.agents.registry import registry
    from ai_office.plugins.loader import load_plugins, _loaded_plugins

    # Загружаем плагины (в реальном приложении это делается в lifespan)
    load_plugins()

    try:
        response = await test_client.get("/api/plugins")
        assert response.status_code == 200
        plugins = response.json()

        # Ищем плагин researcher
        researcher = None
        for plugin in plugins:
            if plugin["name"] == "researcher":
                researcher = plugin
                break

        assert researcher is not None, "Плагин 'researcher' не найден"
        assert researcher["display_name"] == "Researcher"
        assert "tools" in researcher
        assert "search_papers" in researcher["tools"]
        assert "summarize_findings" in researcher["tools"]
    finally:
        # Очистка: удаляем плагин из реестра чтобы не влиять на другие тесты
        if "researcher" in registry._agents:
            del registry._agents["researcher"]
        import ai_office.plugins.loader as _loader
        _loader._loaded_plugins = []


# --- Тест 5: CRUD системных настроек через админ-панель ---


@pytest.mark.asyncio
async def test_admin_settings_crud(test_client: AsyncClient):
    """Проверяет полный CRUD цикл системных настроек через админ-эндпоинты.

    GET получает список, PATCH создает/обновляет, повторный GET подтверждает.
    Работает в owner-режиме (skip_telegram_auth=True).
    """
    # Получаем текущие настройки (может быть пустой список)
    response = await test_client.get("/api/admin/settings")
    assert response.status_code == 200

    # Обновляем настройку
    response = await test_client.patch(
        "/api/admin/settings",
        json={"daily_budget_usd": "25.0"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "daily_budget_usd" in data["updated"]

    # Проверяем, что настройка сохранилась
    response = await test_client.get("/api/admin/settings")
    assert response.status_code == 200
    settings_list = response.json()
    found = False
    for setting in settings_list:
        if setting["key"] == "daily_budget_usd":
            assert setting["value"] == "25.0"
            found = True
            break
    assert found, "Настройка daily_budget_usd не найдена после сохранения"


# --- Тест 6: Обновление агента через админ-панель ---


@pytest.mark.asyncio
async def test_admin_update_agent(test_client: AsyncClient, seed_data):
    """Проверяет обновление system_prompt агента через PATCH /api/admin/agents/{name}.

    Использует seed_data для создания агента Alice, затем обновляет её промпт.
    """
    # Обновляем промпт Alice
    response = await test_client.patch(
        "/api/admin/agents/Alice",
        json={"system_prompt": "Новый промпт для Alice"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["agent"] == "Alice"


# --- Тест 7: Создание Workspace ---


@pytest.mark.asyncio
async def test_workspace_creation(
    async_session: AsyncSession, test_client: AsyncClient
):
    """Проверяет создание рабочего пространства (Workspace) в БД
    и его доступность через GET /api/admin/workspaces.
    """
    # Создаем Workspace напрямую в БД
    workspace = Workspace(
        telegram_chat_id=123456,
        name="Test Office",
        owner_telegram_id=1001,
    )
    async_session.add(workspace)
    await async_session.commit()

    # Проверяем через БД
    result = await async_session.execute(
        select(Workspace).where(Workspace.telegram_chat_id == 123456)
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.name == "Test Office"
    assert saved.owner_telegram_id == 1001

    # Проверяем через API
    response = await test_client.get("/api/admin/workspaces")
    assert response.status_code == 200
    workspaces = response.json()

    found = False
    for ws in workspaces:
        if ws["telegram_chat_id"] == 123456:
            assert ws["name"] == "Test Office"
            assert ws["owner_telegram_id"] == 1001
            found = True
            break
    assert found, "Workspace не найден через API"
