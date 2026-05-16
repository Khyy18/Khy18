"""Тесты планирования, маркетинга и финансов."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_office.core.models import Plan, PlanStep, Agent


# ==================== Тесты моделей ====================

@pytest.mark.asyncio
async def test_plan_model_creation(async_session):
    """Тест: создание модели Plan в БД."""
    plan = Plan(goal="Запустить MVP", status="active")
    async_session.add(plan)
    await async_session.flush()

    assert plan.id is not None
    assert plan.goal == "Запустить MVP"
    assert plan.status == "active"


@pytest.mark.asyncio
async def test_plan_step_model_creation(async_session):
    """Тест: создание модели PlanStep в БД."""
    plan = Plan(goal="Тестовый план", status="active")
    async_session.add(plan)
    await async_session.flush()

    step = PlanStep(
        plan_id=plan.id,
        step_number=1,
        description="Первый шаг",
        status="pending",
    )
    async_session.add(step)
    await async_session.flush()

    assert step.id is not None
    assert step.plan_id == plan.id
    assert step.step_number == 1
    assert step.description == "Первый шаг"
    assert step.status == "pending"
    assert step.result is None


@pytest.mark.asyncio
async def test_plan_steps_relationship(async_session):
    """Тест: связь Plan -> PlanStep работает."""
    plan = Plan(goal="План с шагами", status="active")
    async_session.add(plan)
    await async_session.flush()

    for i in range(3):
        step = PlanStep(
            plan_id=plan.id,
            step_number=i + 1,
            description=f"Шаг {i + 1}",
            status="pending",
        )
        async_session.add(step)
    await async_session.flush()
    await async_session.commit()

    # Проверяем через refresh
    await async_session.refresh(plan)
    assert len(plan.steps) == 3
    assert plan.steps[0].step_number == 1
    assert plan.steps[2].step_number == 3


# ==================== Тесты planning_tools ====================

@pytest.mark.asyncio
async def test_create_plan_tool():
    """Тест: create_plan создаёт план с шагами."""
    from ai_office.tools.planning_tools import create_plan

    with patch("ai_office.tools.planning_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock plan with id after flush
        mock_session.add = MagicMock()
        async def mock_flush():
            # Simulate ID assignment
            for call in mock_session.add.call_args_list:
                obj = call[0][0]
                if isinstance(obj, Plan):
                    obj.id = 1
        mock_session.flush = AsyncMock(side_effect=mock_flush)
        mock_session.commit = AsyncMock()

        # Mock for _log_activity
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await create_plan.ainvoke({
            "goal": "Запустить продукт",
            "steps": "Анализ, Дизайн, Разработка, Тестирование",
        })

        assert "План создан" in result
        assert "Запустить продукт" in result
        assert "Анализ" in result
        assert "Разработка" in result


@pytest.mark.asyncio
async def test_create_plan_empty_steps():
    """Тест: create_plan возвращает ошибку при пустых шагах."""
    from ai_office.tools.planning_tools import create_plan

    with patch("ai_office.tools.planning_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await create_plan.ainvoke({"goal": "Цель", "steps": ""})
        assert "Ошибка" in result


@pytest.mark.asyncio
async def test_execute_next_step_tool():
    """Тест: execute_next_step продвигает план вперёд."""
    from ai_office.tools.planning_tools import execute_next_step

    with patch("ai_office.tools.planning_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1
        mock_plan.status = "active"

        mock_step = MagicMock(spec=PlanStep)
        mock_step.step_number = 1
        mock_step.description = "Анализ требований"
        mock_step.status = "pending"

        mock_next_step = MagicMock(spec=PlanStep)
        mock_next_step.step_number = 2
        mock_next_step.description = "Дизайн"
        mock_next_step.status = "pending"

        # First call returns plan, second returns pending step, third returns next step
        call_count = [0]
        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = mock_plan
            elif call_count[0] == 2:
                mock_result.scalar_one_or_none.return_value = mock_step
            elif call_count[0] == 3:
                mock_result.scalar_one_or_none.return_value = mock_next_step
            else:
                # _log_activity calls
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        result = await execute_next_step.ainvoke({"plan_id": 1})
        assert "Выполнен шаг 1" in result
        assert "Анализ требований" in result
        assert "Следующий шаг 2" in result


@pytest.mark.asyncio
async def test_execute_next_step_plan_not_found():
    """Тест: execute_next_step с несуществующим планом."""
    from ai_office.tools.planning_tools import execute_next_step

    with patch("ai_office.tools.planning_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await execute_next_step.ainvoke({"plan_id": 999})
        assert "не найден" in result


@pytest.mark.asyncio
async def test_get_plan_status_tool():
    """Тест: get_plan_status возвращает форматированный прогресс."""
    from ai_office.tools.planning_tools import get_plan_status

    with patch("ai_office.tools.planning_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1
        mock_plan.goal = "Запустить MVP"
        mock_plan.status = "active"

        mock_step1 = MagicMock(spec=PlanStep)
        mock_step1.step_number = 1
        mock_step1.description = "Анализ"
        mock_step1.status = "done"

        mock_step2 = MagicMock(spec=PlanStep)
        mock_step2.step_number = 2
        mock_step2.description = "Дизайн"
        mock_step2.status = "pending"

        call_count = [0]
        def mock_execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = mock_plan
            elif call_count[0] == 2:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [mock_step1, mock_step2]
                mock_result.scalars.return_value = mock_scalars
            else:
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)
        mock_session.commit = AsyncMock()

        result = await get_plan_status.ainvoke({"plan_id": 1})
        assert "Запустить MVP" in result
        assert "50%" in result
        assert "[x]" in result
        assert "[ ]" in result


# ==================== Тесты регистрации агентов ====================

def test_iris_registered():
    """Тест: Iris зарегистрирована в реестре."""
    from ai_office.agents import registry

    assert "iris" in registry.get_names()
    config = registry.get("iris")
    assert config is not None
    assert config.role == "Marketing & Growth"


def test_oscar_registered():
    """Тест: Oscar зарегистрирован в реестре."""
    from ai_office.agents import registry

    assert "oscar" in registry.get_names()
    config = registry.get("oscar")
    assert config is not None
    assert config.role == "Finance & Operations"


def test_iris_has_delegate_tool():
    """Тест: Iris имеет инструмент делегирования."""
    from ai_office.agents import registry

    config = registry.get("iris")
    tool_names = [t.name for t in config.tools]
    assert "delegate_to_agent" in tool_names


def test_oscar_has_delegate_tool():
    """Тест: Oscar имеет инструмент делегирования."""
    from ai_office.agents import registry

    config = registry.get("oscar")
    tool_names = [t.name for t in config.tools]
    assert "delegate_to_agent" in tool_names


def test_iris_has_specialized_tools():
    """Тест: Iris имеет как минимум 3 специализированных инструмента."""
    from ai_office.agents import registry

    common_tool_names = {
        "create_task", "update_task_status", "assign_task",
        "get_active_tasks", "delegate_to_agent",
    }
    config = registry.get("iris")
    specialized = [t for t in config.tools if t.name not in common_tool_names]
    assert len(specialized) >= 3


def test_oscar_has_specialized_tools():
    """Тест: Oscar имеет как минимум 3 специализированных инструмента."""
    from ai_office.agents import registry

    common_tool_names = {
        "create_task", "update_task_status", "assign_task",
        "get_active_tasks", "delegate_to_agent",
    }
    config = registry.get("oscar")
    specialized = [t for t in config.tools if t.name not in common_tool_names]
    assert len(specialized) >= 3


def test_alice_has_planning_tools():
    """Тест: Alice имеет инструменты планирования."""
    from ai_office.agents import registry

    config = registry.get("alice")
    tool_names = [t.name for t in config.tools]
    assert "create_plan" in tool_names
    assert "execute_next_step" in tool_names
    assert "get_plan_status" in tool_names


def test_sam_has_planning_tools():
    """Тест: Sam имеет инструменты планирования."""
    from ai_office.agents import registry

    config = registry.get("sam")
    tool_names = [t.name for t in config.tools]
    assert "create_plan" in tool_names
    assert "execute_next_step" in tool_names
    assert "get_plan_status" in tool_names


# ==================== Тесты маркетинговых инструментов ====================

@pytest.mark.asyncio
async def test_analyze_seo_with_mocked_httpx():
    """Тест: analyze_seo с мок-ответом httpx."""
    from ai_office.tools.marketing_tools import analyze_seo

    html_response = """
    <html>
    <head>
        <title>Тестовая страница для SEO</title>
        <meta name="description" content="Это тестовое описание страницы для проверки SEO анализа">
    </head>
    <body>
        <h1>Заголовок</h1>
        <p>Контент страницы с текстом</p>
    </body>
    </html>
    """

    with patch("ai_office.tools.marketing_tools.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_response = MagicMock()
        mock_response.text = html_response
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ai_office.tools.marketing_tools._log_activity", new_callable=AsyncMock):
            result = await analyze_seo.ainvoke({"url": "https://example.com"})

        assert "SEO-анализ" in result
        assert "Тестовая страница для SEO" in result


@pytest.mark.asyncio
async def test_analyze_seo_fetch_error():
    """Тест: analyze_seo при ошибке загрузки возвращает общие рекомендации."""
    from ai_office.tools.marketing_tools import analyze_seo

    with patch("ai_office.tools.marketing_tools.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(side_effect=Exception("Connection error"))

        with patch("ai_office.tools.marketing_tools._log_activity", new_callable=AsyncMock):
            result = await analyze_seo.ainvoke({"url": "https://unreachable.test"})

        assert "рекомендации" in result.lower() or "Не удалось" in result


@pytest.mark.asyncio
async def test_generate_content_plan_weekly():
    """Тест: generate_content_plan для недели."""
    from ai_office.tools.marketing_tools import generate_content_plan

    with patch("ai_office.tools.marketing_tools._log_activity", new_callable=AsyncMock):
        result = await generate_content_plan.ainvoke({"topic": "AI", "period": "неделя"})

    assert "Контент-план на неделю" in result
    assert "AI" in result
    assert "Понедельник" in result


@pytest.mark.asyncio
async def test_generate_content_plan_monthly():
    """Тест: generate_content_plan для месяца."""
    from ai_office.tools.marketing_tools import generate_content_plan

    with patch("ai_office.tools.marketing_tools._log_activity", new_callable=AsyncMock):
        result = await generate_content_plan.ainvoke({"topic": "SaaS", "period": "месяц"})

    assert "Контент-план на месяц" in result
    assert "SaaS" in result
    assert "Неделя 1" in result


@pytest.mark.asyncio
async def test_suggest_ab_test():
    """Тест: suggest_ab_test возвращает предложение теста."""
    from ai_office.tools.marketing_tools import suggest_ab_test

    with patch("ai_office.tools.marketing_tools._log_activity", new_callable=AsyncMock):
        result = await suggest_ab_test.ainvoke({"feature": "кнопка регистрации"})

    assert "A/B тест" in result
    assert "кнопка регистрации" in result
    assert "Гипотеза" in result
    assert "Метрики" in result


# ==================== Тесты финансовых инструментов ====================

@pytest.mark.asyncio
async def test_calculate_budget():
    """Тест: calculate_budget корректно парсит и суммирует."""
    from ai_office.tools.finance_tools import calculate_budget

    with patch("ai_office.tools.finance_tools._log_activity", new_callable=AsyncMock):
        result = await calculate_budget.ainvoke({
            "items": "Хостинг:5000,Дизайн:15000,Разработка:50000"
        })

    assert "Бюджет" in result
    assert "Хостинг" in result
    assert "70000" in result  # total
    assert "ИТОГО" in result


@pytest.mark.asyncio
async def test_calculate_budget_invalid_format():
    """Тест: calculate_budget обрабатывает невалидный ввод."""
    from ai_office.tools.finance_tools import calculate_budget

    with patch("ai_office.tools.finance_tools._log_activity", new_callable=AsyncMock):
        result = await calculate_budget.ainvoke({"items": "некорректный формат"})

    assert "Ошибка" in result or "Неверный" in result.lower() or "ошибка" in result.lower()


@pytest.mark.asyncio
async def test_generate_invoice():
    """Тест: generate_invoice создаёт форматированный счёт."""
    from ai_office.tools.finance_tools import generate_invoice

    with patch("ai_office.tools.finance_tools._log_activity", new_callable=AsyncMock):
        result = await generate_invoice.ainvoke({
            "client": "ООО Рога и Копыта",
            "items": "Разработка сайта:100000,Дизайн:30000",
            "currency": "RUB",
        })

    assert "СЧЁТ" in result
    assert "ООО Рога и Копыта" in result
    assert "130000" in result
    assert "руб." in result


@pytest.mark.asyncio
async def test_generate_invoice_usd():
    """Тест: generate_invoice с валютой USD."""
    from ai_office.tools.finance_tools import generate_invoice

    with patch("ai_office.tools.finance_tools._log_activity", new_callable=AsyncMock):
        result = await generate_invoice.ainvoke({
            "client": "Acme Corp",
            "items": "Consulting:5000",
            "currency": "USD",
        })

    assert "Acme Corp" in result
    assert "$" in result


@pytest.mark.asyncio
async def test_cost_analysis():
    """Тест: cost_analysis возвращает шаблон анализа."""
    from ai_office.tools.finance_tools import cost_analysis

    with patch("ai_office.tools.finance_tools._log_activity", new_callable=AsyncMock):
        result = await cost_analysis.ainvoke({"period": "квартал"})

    assert "Анализ затрат" in result
    assert "квартал" in result
    assert "Постоянные расходы" in result
    assert "Рекомендации" in result
