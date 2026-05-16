"""Тесты OnboardingManager - state machine, переходы, финализация."""

import json

import pytest
import pytest_asyncio
from sqlalchemy import select

from ai_office.core.models import Workspace
from ai_office.core.onboarding import OnboardingManager, ONBOARDING_STEPS


@pytest_asyncio.fixture
async def workspace(async_session):
    """Создать тестовое рабочее пространство."""
    ws = Workspace(
        telegram_chat_id=123456789,
        name="Test Workspace",
        owner_telegram_id=111222333,
    )
    async_session.add(ws)
    await async_session.commit()
    await async_session.refresh(ws)
    return ws


@pytest.mark.asyncio
async def test_start_onboarding(async_session, workspace):
    """Тест начала онбординга - возвращает первый вопрос."""
    manager = OnboardingManager()
    result = await manager.start_onboarding(async_session, workspace.id)

    assert result["step"] == 1
    assert result["question"] == "Чем занимается ваша команда?"
    assert "Development" in result["options"]
    assert "Marketing" in result["options"]
    assert "Design" in result["options"]
    assert "Mixed" in result["options"]


@pytest.mark.asyncio
async def test_start_onboarding_sets_state(async_session, workspace):
    """Тест: start_onboarding сохраняет состояние в settings_json."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)

    await async_session.refresh(workspace)
    settings = json.loads(workspace.settings_json)
    assert settings["onboarding"]["current_step"] == 1
    assert settings["onboarding"]["completed"] is False


@pytest.mark.asyncio
async def test_handle_response_step1_returns_step2(async_session, workspace):
    """Тест: ответ на шаг 1 возвращает шаг 2."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)

    result = await manager.handle_onboarding_response(
        async_session, workspace.id, step=1, answer="Development"
    )

    assert result is not None
    assert result["step"] == 2
    assert result["question"] == "Сколько человек в команде?"


@pytest.mark.asyncio
async def test_handle_response_step2_returns_step3(async_session, workspace):
    """Тест: ответ на шаг 2 возвращает шаг 3."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=1, answer="Development"
    )

    result = await manager.handle_onboarding_response(
        async_session, workspace.id, step=2, answer="4-10"
    )

    assert result is not None
    assert result["step"] == 3
    assert result["question"] == "Какие задачи хотите автоматизировать?"


@pytest.mark.asyncio
async def test_handle_response_step3_finalizes(async_session, workspace):
    """Тест: ответ на шаг 3 завершает онбординг (возвращает None)."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=1, answer="Development"
    )
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=2, answer="4-10"
    )

    result = await manager.handle_onboarding_response(
        async_session, workspace.id, step=3, answer="Code review"
    )

    assert result is None


@pytest.mark.asyncio
async def test_finalize_onboarding_configures_workspace(async_session, workspace):
    """Тест: finalize_onboarding настраивает workspace корректно."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=1, answer="Development"
    )
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=2, answer="4-10"
    )
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=3, answer="Code review"
    )

    await async_session.refresh(workspace)
    settings = json.loads(workspace.settings_json)

    # Development team agents
    assert "sam" in settings["enabled_agents"]
    assert "alice" in settings["enabled_agents"]
    assert "leo" in settings["enabled_agents"]
    assert "nova" in settings["enabled_agents"]

    # Team size 4-10 = 8 concurrent tasks
    assert settings["max_concurrent_tasks"] == 8

    # Code review automation
    assert settings["automation"]["code_review_enabled"] is True


@pytest.mark.asyncio
async def test_finalize_onboarding_marketing_team(async_session, workspace):
    """Тест: финализация для Marketing команды."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=1, answer="Marketing"
    )
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=2, answer="1-3"
    )
    await manager.handle_onboarding_response(
        async_session, workspace.id, step=3, answer="Content"
    )

    await async_session.refresh(workspace)
    settings = json.loads(workspace.settings_json)

    assert "iris" in settings["enabled_agents"]
    assert settings["max_concurrent_tasks"] == 3
    assert settings["automation"]["content_calendar"] is True


@pytest.mark.asyncio
async def test_start_onboarding_invalid_workspace(async_session):
    """Тест: start_onboarding для несуществующего workspace."""
    manager = OnboardingManager()
    with pytest.raises(ValueError, match="not found"):
        await manager.start_onboarding(async_session, 99999)


@pytest.mark.asyncio
async def test_handle_response_invalid_step(async_session, workspace):
    """Тест: handle_onboarding_response с невалидным шагом."""
    manager = OnboardingManager()
    await manager.start_onboarding(async_session, workspace.id)

    with pytest.raises(ValueError, match="Invalid step"):
        await manager.handle_onboarding_response(
            async_session, workspace.id, step=99, answer="test"
        )
