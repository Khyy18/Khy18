"""Тесты для модуля автоматизации фриланс-площадок."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from freelance_automation.base import Order, FreelancePlatform
from freelance_automation import scheduler as scheduler_module
from freelance_automation.scheduler import FreelanceScheduler
from freelance_automation.config import (
    MAX_RESPONSES_PER_HOUR,
    RESPONSE_TEMPLATES,
    SCAN_INTERVAL_MINUTES,
)


@pytest.fixture(autouse=True)
def _isolate_dedup(tmp_path):
    """Use a temp dedup path for each test to prevent cross-test interference."""
    dedup_path = str(tmp_path / "dedup.json")
    with patch.object(scheduler_module, "DEDUP_PATH", dedup_path):
        yield


# --- Тесты Order dataclass ---


def test_order_creation():
    """Order создаётся с обязательными полями."""
    order = Order(
        id="123",
        title="Разработка сайта",
        description="Нужен сайт на Python",
        budget=5000.0,
        url="https://kwork.ru/projects/123",
    )
    assert order.id == "123"
    assert order.title == "Разработка сайта"
    assert order.description == "Нужен сайт на Python"
    assert order.budget == 5000.0
    assert order.url == "https://kwork.ru/projects/123"
    assert order.posted_at is None


def test_order_with_posted_at():
    """Order принимает опциональное поле posted_at."""
    now = datetime.now(timezone.utc)
    order = Order(
        id="456",
        title="Тест",
        description="Описание",
        budget=None,
        url="https://fl.ru/projects/456",
        posted_at=now,
    )
    assert order.posted_at == now
    assert order.budget is None


# --- Тесты шаблонов откликов ---


def test_pick_template_fills_placeholders():
    """_pick_template подставляет title и budget в шаблон."""
    order = Order(
        id="1",
        title="Создание бота",
        description="",
        budget=3000.0,
        url="https://kwork.ru/1",
    )
    scheduler = FreelanceScheduler(platforms=[], keywords=[])
    result = scheduler._pick_template(order)

    assert "Создание бота" in result
    assert "3000" in result


def test_pick_template_no_budget():
    """_pick_template обрабатывает отсутствие бюджета."""
    order = Order(
        id="2",
        title="Дизайн логотипа",
        description="",
        budget=None,
        url="https://fl.ru/2",
    )
    scheduler = FreelanceScheduler(platforms=[], keywords=[])
    result = scheduler._pick_template(order)

    assert "Дизайн логотипа" in result
    assert "договорный" in result


# --- Тесты run_once с мок-платформами ---


@pytest.mark.asyncio
async def test_run_once_responds_to_orders():
    """run_once вызывает fetch_new_orders и respond_to_order для каждого заказа."""
    mock_platform = AsyncMock(spec=FreelancePlatform)
    mock_platform.fetch_new_orders = AsyncMock(return_value=[
        Order(id="1", title="Проект 1", description="Описание 1", budget=1000.0, url="http://test/1"),
        Order(id="2", title="Проект 2", description="Описание 2", budget=2000.0, url="http://test/2"),
    ])
    mock_platform.respond_to_order = AsyncMock(return_value=True)

    scheduler = FreelanceScheduler(platforms=[mock_platform], keywords=[])
    await scheduler.run_once()

    assert mock_platform.fetch_new_orders.call_count == 1
    assert mock_platform.respond_to_order.call_count == 2


@pytest.mark.asyncio
async def test_run_once_with_keywords_filter():
    """run_once передаёт keywords в fetch_new_orders."""
    mock_platform = AsyncMock(spec=FreelancePlatform)
    mock_platform.fetch_new_orders = AsyncMock(return_value=[])
    mock_platform.respond_to_order = AsyncMock(return_value=True)

    keywords = ["python", "бот"]
    scheduler = FreelanceScheduler(platforms=[mock_platform], keywords=keywords)
    await scheduler.run_once()

    mock_platform.fetch_new_orders.assert_called_once_with(keywords=keywords)


@pytest.mark.asyncio
async def test_run_once_empty_keywords():
    """run_once передаёт None если keywords пустой."""
    mock_platform = AsyncMock(spec=FreelancePlatform)
    mock_platform.fetch_new_orders = AsyncMock(return_value=[])
    mock_platform.respond_to_order = AsyncMock(return_value=True)

    scheduler = FreelanceScheduler(platforms=[mock_platform], keywords=[])
    await scheduler.run_once()

    mock_platform.fetch_new_orders.assert_called_once_with(keywords=None)


# --- Тесты лимита откликов ---


@pytest.mark.asyncio
async def test_max_responses_per_hour_limit():
    """Планировщик соблюдает лимит MAX_RESPONSES_PER_HOUR."""
    mock_platform = AsyncMock(spec=FreelancePlatform)

    # Создаём больше заказов чем лимит
    orders = [
        Order(
            id=str(i),
            title=f"Заказ {i}",
            description="Описание",
            budget=1000.0,
            url=f"http://test/{i}",
        )
        for i in range(MAX_RESPONSES_PER_HOUR + 5)
    ]
    mock_platform.fetch_new_orders = AsyncMock(return_value=orders)
    mock_platform.respond_to_order = AsyncMock(return_value=True)

    scheduler = FreelanceScheduler(platforms=[mock_platform], keywords=[])
    await scheduler.run_once()

    # Не больше MAX_RESPONSES_PER_HOUR откликов
    assert mock_platform.respond_to_order.call_count == MAX_RESPONSES_PER_HOUR


@pytest.mark.asyncio
async def test_responses_counter_tracks_time():
    """Счётчик откликов учитывает время (старые записи удаляются)."""
    mock_platform = AsyncMock(spec=FreelancePlatform)
    mock_platform.fetch_new_orders = AsyncMock(return_value=[
        Order(id="1", title="Заказ", description="", budget=100.0, url="http://test/1"),
    ])
    mock_platform.respond_to_order = AsyncMock(return_value=True)

    scheduler = FreelanceScheduler(platforms=[mock_platform], keywords=[])

    # Добавляем старые записи (старше часа)
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    scheduler._responses_this_hour = [old_time] * MAX_RESPONSES_PER_HOUR

    await scheduler.run_once()

    # Старые записи очистились, новый отклик отправлен
    assert mock_platform.respond_to_order.call_count == 1


# --- Тесты конфигурации ---


def test_config_defaults():
    """Проверка значений по умолчанию в конфигурации."""
    assert SCAN_INTERVAL_MINUTES == 5
    assert MAX_RESPONSES_PER_HOUR == 10
    assert len(RESPONSE_TEMPLATES) == 3


def test_response_templates_have_placeholders():
    """Все шаблоны содержат плейсхолдеры {title} и {budget}."""
    for template in RESPONSE_TEMPLATES:
        assert "{title}" in template
        assert "{budget}" in template
