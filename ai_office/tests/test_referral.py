"""Тесты реферальной системы и карточек шаринга."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from ai_office.core.models import Referral, Task, Agent
from ai_office.core.referral import (
    apply_referral,
    generate_referral_code,
    get_referral_stats,
)
from ai_office.core.share_cards import generate_task_card


# --- Unit tests for referral logic ---


@pytest.mark.asyncio
async def test_generate_referral_code_length(async_session):
    """generate_referral_code возвращает 8-символьный код."""
    code = await generate_referral_code(111111, async_session)
    assert len(code) == 8
    assert code.isalnum()


@pytest.mark.asyncio
async def test_generate_referral_code_idempotent(async_session):
    """Повторный вызов для того же пользователя возвращает тот же код."""
    code1 = await generate_referral_code(222222, async_session)
    code2 = await generate_referral_code(222222, async_session)
    assert code1 == code2


@pytest.mark.asyncio
async def test_apply_referral_valid(async_session):
    """Применение валидного кода дает L1 бонус."""
    code = await generate_referral_code(100001, async_session)
    result = await apply_referral(200001, code, async_session)
    assert result["success"] is True
    assert result["bonus_granted"] == 100


@pytest.mark.asyncio
async def test_apply_referral_self(async_session):
    """Нельзя использовать свой собственный код."""
    code = await generate_referral_code(300001, async_session)
    result = await apply_referral(300001, code, async_session)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_apply_referral_invalid_code(async_session):
    """Невалидный код возвращает ошибку."""
    result = await apply_referral(400001, "BADCODE1", async_session)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_apply_referral_double_use(async_session):
    """Код нельзя использовать дважды."""
    code = await generate_referral_code(500001, async_session)
    await apply_referral(600001, code, async_session)
    result = await apply_referral(700001, code, async_session)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_apply_referral_chain_l2(async_session):
    """3-уровневая цепочка: L2 бонус."""
    # User A приглашает User B
    code_a = await generate_referral_code(1001, async_session)
    await apply_referral(1002, code_a, async_session)

    # User B приглашает User C -> A получает L2 бонус
    code_b = await generate_referral_code(1002, async_session)
    result = await apply_referral(1003, code_b, async_session)
    assert result["success"] is True
    assert result["bonus_granted"] == 150  # 100 (L1 for B) + 50 (L2 for A)


@pytest.mark.asyncio
async def test_apply_referral_chain_l3(async_session):
    """3-уровневая цепочка: L3 бонус."""
    # User A приглашает User B
    code_a = await generate_referral_code(2001, async_session)
    await apply_referral(2002, code_a, async_session)

    # User B приглашает User C
    code_b = await generate_referral_code(2002, async_session)
    await apply_referral(2003, code_b, async_session)

    # User C приглашает User D -> A получает L3, B получает L2
    code_c = await generate_referral_code(2003, async_session)
    result = await apply_referral(2004, code_c, async_session)
    assert result["success"] is True
    assert result["bonus_granted"] == 175  # 100 (L1 for C) + 50 (L2 for B) + 25 (L3 for A)


@pytest.mark.asyncio
async def test_get_referral_stats(async_session):
    """get_referral_stats возвращает корректную статистику."""
    # User A приглашает двух пользователей
    code = await generate_referral_code(3001, async_session)
    await apply_referral(3002, code, async_session)

    # Генерируем новый код для второго приглашения
    # (первый код уже использован, нужен новый)
    from ai_office.core.referral import _generate_code
    from ai_office.core.models import Referral

    new_code = _generate_code()
    ref2 = Referral(
        referrer_telegram_id=3001,
        referral_code=new_code,
        level=1,
    )
    async_session.add(ref2)
    await async_session.commit()

    await apply_referral(3003, new_code, async_session)

    stats = await get_referral_stats(3001, async_session)
    assert stats["direct_referrals"] == 2
    assert stats["total_bonus"] == 200


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_api_referral_code(test_client: AsyncClient):
    """GET /api/referral/code возвращает 200 с кодом."""
    response = await test_client.get("/api/referral/code")
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "referral_link" in data
    assert len(data["code"]) == 8


@pytest.mark.asyncio
async def test_api_referral_stats(test_client: AsyncClient):
    """GET /api/referral/stats возвращает 200 со статистикой."""
    response = await test_client.get("/api/referral/stats")
    assert response.status_code == 200
    data = response.json()
    assert "direct_referrals" in data
    assert "level_2" in data
    assert "level_3" in data
    assert "total_bonus" in data


@pytest.mark.asyncio
async def test_api_referral_apply_invalid(test_client: AsyncClient):
    """POST /api/referral/apply с невалидным кодом."""
    response = await test_client.post(
        "/api/referral/apply", json={"code": "INVALID1"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_api_referral_apply_valid(test_client: AsyncClient, async_session):
    """POST /api/referral/apply с валидным кодом."""
    # Создаем реферальный код для другого пользователя
    code = await generate_referral_code(999999, async_session)

    response = await test_client.post(
        "/api/referral/apply", json={"code": code}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["bonus_granted"] == 100


# --- Share card tests ---


@pytest.mark.asyncio
async def test_generate_task_card_not_found(async_session):
    """generate_task_card для несуществующей задачи."""
    card = await generate_task_card(99999, async_session)
    assert card["share_text"] == "Задача не найдена"


@pytest.mark.asyncio
async def test_generate_task_card_with_task(async_session):
    """generate_task_card возвращает данные карточки."""
    agent = Agent(
        name="TestAgent",
        role="Тестовый",
        system_prompt="test",
        status="idle",
    )
    async_session.add(agent)
    await async_session.flush()

    task = Task(
        description="Тестовая задача для карточки",
        creator_type="user",
        creator_id="user_1",
        executor_id=agent.id,
        status="done",
        priority="high",
    )
    async_session.add(task)
    await async_session.commit()

    card = await generate_task_card(task.id, async_session)
    assert card["task_description"] == "Тестовая задача для карточки"
    assert card["agent_name"] == "TestAgent"
    assert card["priority"] == "Высокий"
    assert "AI Office" in card["share_text"]


@pytest.mark.asyncio
async def test_api_share_task(test_client: AsyncClient, async_session):
    """GET /api/share/task/{id} возвращает карточку."""
    task = Task(
        description="Задача для API теста",
        creator_type="user",
        creator_id="user_test",
        status="open",
        priority="medium",
    )
    async_session.add(task)
    await async_session.commit()

    response = await test_client.get(f"/api/share/task/{task.id}")
    assert response.status_code == 200
    data = response.json()
    assert "task_description" in data
    assert "share_text" in data


@pytest.mark.asyncio
async def test_api_share_task_not_found(test_client: AsyncClient):
    """GET /api/share/task/{id} для несуществующей задачи."""
    response = await test_client.get("/api/share/task/99999")
    assert response.status_code == 200
    data = response.json()
    assert data["share_text"] == "Задача не найдена"
