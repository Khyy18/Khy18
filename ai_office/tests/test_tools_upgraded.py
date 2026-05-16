"""Тесты обновленных инструментов (qa_tools, analytics_tools, design_tools)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_session():
    """Создать мок async_session для тестов."""
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session_factory, mock_session


# === Тесты qa_tools ===


@pytest.mark.asyncio
async def test_create_test_plan_structured_sections():
    """Тест: create_test_plan возвращает структурированные разделы."""
    from ai_office.tools.qa_tools import create_test_plan

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await create_test_plan.ainvoke({"feature": "Авторизация пользователя"})

    assert "Позитивные сценарии" in result
    assert "Негативные сценарии" in result
    assert "Граничные случаи" in result
    assert "Производительность" in result
    assert "Авторизация пользователя" in result


@pytest.mark.asyncio
async def test_create_test_plan_auth_keywords():
    """Тест: create_test_plan генерирует релевантные сценарии для авторизации."""
    from ai_office.tools.qa_tools import create_test_plan

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await create_test_plan.ainvoke({"feature": "Форма логина с auth"})

    assert "вход" in result.lower() or "пароль" in result.lower() or "авториз" in result.lower()


@pytest.mark.asyncio
async def test_create_test_plan_search_keywords():
    """Тест: create_test_plan генерирует релевантные сценарии для поиска."""
    from ai_office.tools.qa_tools import create_test_plan

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await create_test_plan.ainvoke({"feature": "Поиск по каталогу"})

    assert "поиск" in result.lower() or "результат" in result.lower()


@pytest.mark.asyncio
async def test_report_bug_creates_task_in_db():
    """Тест: report_bug создает Task в БД и возвращает ID."""
    from ai_office.tools.qa_tools import report_bug

    mock_session_factory, mock_session = _make_mock_session()

    # Мокаем refresh чтобы вернуть task с id
    mock_task = MagicMock()
    mock_task.id = 42

    async def mock_refresh(obj):
        obj.id = 42

    mock_session.refresh = mock_refresh

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await report_bug.ainvoke({
            "title": "Кнопка не работает",
            "steps": "1. Открыть страницу\n2. Нажать кнопку",
            "expected": "Форма отправляется",
            "actual": "Ничего не происходит",
            "severity": "major",
        })

    assert "#42" in result
    assert "Кнопка не работает" in result
    assert "major" in result
    assert "medium" in result  # mapped priority
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_report_bug_severity_mapping():
    """Тест: report_bug корректно маппит severity -> priority."""
    from ai_office.tools.qa_tools import report_bug

    mock_session_factory, mock_session = _make_mock_session()

    async def mock_refresh(obj):
        obj.id = 1

    mock_session.refresh = mock_refresh

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await report_bug.ainvoke({
            "title": "Critical bug",
            "steps": "steps",
            "expected": "expected",
            "actual": "actual",
            "severity": "blocker",
        })

    assert "critical" in result  # blocker -> critical priority


@pytest.mark.asyncio
async def test_verify_fix_task_found():
    """Тест: verify_fix находит задачу и возвращает чеклист."""
    from ai_office.tools.qa_tools import verify_fix

    mock_session_factory, mock_session = _make_mock_session()

    mock_task = MagicMock()
    mock_task.id = 5
    mock_task.description = "Bug description"
    mock_task.status = "in_progress"
    mock_task.priority = "high"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await verify_fix.ainvoke({"bug_id": "5"})

    assert "#5" in result
    assert "in_progress" in result
    assert "Чеклист верификации" in result
    assert "Регрессионные тесты" in result


@pytest.mark.asyncio
async def test_verify_fix_task_not_found():
    """Тест: verify_fix обрабатывает несуществующую задачу."""
    from ai_office.tools.qa_tools import verify_fix

    mock_session_factory, mock_session = _make_mock_session()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("ai_office.tools.qa_tools.async_session", mock_session_factory):
        result = await verify_fix.ainvoke({"bug_id": "999"})

    assert "не найдена" in result


# === Тесты analytics_tools ===


@pytest.mark.asyncio
async def test_create_user_story_given_when_then():
    """Тест: create_user_story генерирует формат Given/When/Then."""
    from ai_office.tools.analytics_tools import create_user_story

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.analytics_tools.async_session", mock_session_factory):
        result = await create_user_story.ainvoke({
            "role": "менеджер",
            "action": "просматривать отчеты",
            "benefit": "принимать обоснованные решения",
        })

    assert "Как менеджер" in result
    assert "просматривать отчеты" in result
    assert "принимать обоснованные решения" in result
    assert "Given" in result
    assert "When" in result
    assert "Then" in result


@pytest.mark.asyncio
async def test_analyze_requirements_categorizes_functional():
    """Тест: analyze_requirements определяет функциональные требования."""
    from ai_office.tools.analytics_tools import analyze_requirements

    mock_session_factory, mock_session = _make_mock_session()

    text = "Система должна отображать список задач.\nВремя отклика не более 2 секунд."

    with patch("ai_office.tools.analytics_tools.async_session", mock_session_factory):
        result = await analyze_requirements.ainvoke({"text": text})

    assert "Функциональные требования" in result
    assert "Нефункциональные требования" in result or "Ограничения" in result


@pytest.mark.asyncio
async def test_analyze_requirements_categorizes_non_functional():
    """Тест: analyze_requirements определяет нефункциональные требования."""
    from ai_office.tools.analytics_tools import analyze_requirements

    mock_session_factory, mock_session = _make_mock_session()

    text = "Обеспечить безопасность данных пользователей.\nПроизводительность системы при нагрузке 1000 пользователей."

    with patch("ai_office.tools.analytics_tools.async_session", mock_session_factory):
        result = await analyze_requirements.ainvoke({"text": text})

    assert "Нефункциональные требования" in result
    # Should categorize at least one as non-functional
    assert "(не обнаружены)" not in result.split("Нефункциональные требования")[1].split("##")[0]


@pytest.mark.asyncio
async def test_analyze_requirements_categorizes_constraints():
    """Тест: analyze_requirements определяет ограничения."""
    from ai_office.tools.analytics_tools import analyze_requirements

    mock_session_factory, mock_session = _make_mock_session()

    text = "Размер файла не более 10MB.\nОбязательная двухфакторная аутентификация."

    with patch("ai_office.tools.analytics_tools.async_session", mock_session_factory):
        result = await analyze_requirements.ainvoke({"text": text})

    assert "Ограничения" in result


@pytest.mark.asyncio
async def test_generate_report_queries_db():
    """Тест: generate_report запрашивает данные из БД."""
    from ai_office.tools.analytics_tools import generate_report

    mock_session_factory, mock_session = _make_mock_session()

    # Mock task stats query
    mock_task_result = MagicMock()
    mock_task_result.all.return_value = [("open", 5), ("closed", 3)]

    # Mock activity count query
    mock_activity_result = MagicMock()
    mock_activity_result.scalar.return_value = 15

    # Mock token usage query
    mock_token_result = MagicMock()
    mock_token_row = MagicMock()
    mock_token_row.__getitem__ = lambda self, idx: [1000, 500, 0.05][idx]
    mock_token_result.one.return_value = mock_token_row

    # _log_activity also calls execute (to find agent), so we need an extra result
    mock_agent_result = MagicMock()
    mock_agent_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(
        side_effect=[
            mock_task_result,
            mock_activity_result,
            mock_token_result,
            mock_agent_result,
        ]
    )

    with patch("ai_office.tools.analytics_tools.async_session", mock_session_factory):
        result = await generate_report.ainvoke({"type": "summary", "period": "неделя"})

    assert "Задачи" in result
    assert "Активность" in result
    assert "Использование токенов" in result
    assert "неделя" in result
    # Verify DB was queried (3 for report + 1 for _log_activity)
    assert mock_session.execute.call_count == 4


# === Тесты design_tools ===


@pytest.mark.asyncio
async def test_review_design_structured_categories():
    """Тест: review_design возвращает все четыре категории."""
    from ai_office.tools.design_tools import review_design

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await review_design.ainvoke({
            "description": "Модальное окно с формой ввода и кнопками"
        })

    assert "Доступность" in result
    assert "Консистентность" in result
    assert "Мобильная адаптивность" in result or "Mobile" in result
    assert "Контраст" in result


@pytest.mark.asyncio
async def test_review_design_contextual_recommendations():
    """Тест: review_design генерирует контекстные рекомендации для кнопок."""
    from ai_office.tools.design_tools import review_design

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await review_design.ainvoke({
            "description": "Экран с кнопками и таблицей данных в темной теме"
        })

    assert "44x44" in result  # button touch target
    assert "темн" in result.lower() or "4.5:1" in result


@pytest.mark.asyncio
async def test_generate_wireframe_ascii_art():
    """Тест: generate_wireframe генерирует ASCII-вайрфрейм с символами рамок."""
    from ai_office.tools.design_tools import generate_wireframe

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await generate_wireframe.ainvoke({
            "screen_name": "Список задач",
            "requirements": "Отобразить список задач с фильтрацией",
        })

    # Should contain box drawing characters
    assert "+" in result
    assert "-" in result
    assert "|" in result
    assert "Список задач" in result
    assert "list" in result.lower()


@pytest.mark.asyncio
async def test_generate_wireframe_form_pattern():
    """Тест: generate_wireframe определяет паттерн формы."""
    from ai_office.tools.design_tools import generate_wireframe

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await generate_wireframe.ainvoke({
            "screen_name": "Регистрация",
            "requirements": "Форма регистрации с полями ввода email и пароля",
        })

    assert "form" in result.lower()
    assert "+" in result
    assert "|" in result


@pytest.mark.asyncio
async def test_generate_wireframe_dashboard_pattern():
    """Тест: generate_wireframe определяет паттерн дашборда."""
    from ai_office.tools.design_tools import generate_wireframe

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await generate_wireframe.ainvoke({
            "screen_name": "Dashboard",
            "requirements": "Панель с метриками и статистикой",
        })

    assert "dashboard" in result.lower()


@pytest.mark.asyncio
async def test_suggest_ux_improvements_detects_no_feedback():
    """Тест: suggest_ux_improvements обнаруживает отсутствие обратной связи."""
    from ai_office.tools.design_tools import suggest_ux_improvements

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await suggest_ux_improvements.ainvoke({
            "current_flow": "Пользователь нажимает кнопку отправки и ждет"
        })

    assert "Обнаружено проблем" in result
    assert "обратн" in result.lower() or "индикатор" in result.lower()


@pytest.mark.asyncio
async def test_suggest_ux_improvements_detects_no_undo():
    """Тест: suggest_ux_improvements обнаруживает невозможность отмены."""
    from ai_office.tools.design_tools import suggest_ux_improvements

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await suggest_ux_improvements.ainvoke({
            "current_flow": "Пользователь удаляет запись без подтверждения"
        })

    assert "Обнаружено проблем" in result
    assert "отмен" in result.lower() or "подтвержд" in result.lower()


@pytest.mark.asyncio
async def test_suggest_ux_improvements_detects_too_many_steps():
    """Тест: suggest_ux_improvements обнаруживает слишком много шагов."""
    from ai_office.tools.design_tools import suggest_ux_improvements

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await suggest_ux_improvements.ainvoke({
            "current_flow": "Шаг 1: открыть меню, шаг 2: выбрать раздел, шаг 3: нажать далее, шаг 4: заполнить форму"
        })

    assert "Обнаружено проблем" in result
    assert len(result) > 100  # Should contain actual recommendations


@pytest.mark.asyncio
async def test_suggest_ux_improvements_no_issues():
    """Тест: suggest_ux_improvements корректно обрабатывает отсутствие проблем."""
    from ai_office.tools.design_tools import suggest_ux_improvements

    mock_session_factory, mock_session = _make_mock_session()

    with patch("ai_office.tools.design_tools.async_session", mock_session_factory):
        result = await suggest_ux_improvements.ainvoke({
            "current_flow": "Простой интерфейс"
        })

    assert "0" in result or "не обнаружено" in result.lower()
