"""Тесты для AI-респондера и портфолио фриланс-автоматизации."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from freelance_automation.ai_responder import AIResponder
from freelance_automation.base import Order
from freelance_automation.portfolio import select_relevant


@pytest.fixture
def sample_order():
    """Тестовый заказ."""
    return Order(
        id="test-123",
        title="Разработка Telegram бота для CRM",
        description="Нужен бот с интеграцией платежей и базой данных",
        budget=50000.0,
        url="https://example.com/order/123",
    )


@pytest.fixture
def crypto_order():
    """Тестовый заказ на крипто-тему."""
    return Order(
        id="test-456",
        title="Торговый бот для криптовалют",
        description="Автоматическая торговля crypto на бирже",
        budget=100000.0,
        url="https://example.com/order/456",
    )


@pytest.fixture
def no_match_order():
    """Заказ без совпадений с портфолио."""
    return Order(
        id="test-789",
        title="Дизайн визиток",
        description="Нужен дизайн визиток для стоматологии",
        budget=5000.0,
        url="https://example.com/order/789",
    )


class TestAIResponder:
    """Тесты генерации AI-откликов."""

    @pytest.mark.asyncio
    async def test_generate_response_success(self, sample_order):
        """AI генерирует непустой ответ."""
        mock_response = "Здравствуйте! Имею опыт разработки Telegram-ботов."
        with patch("ai_router.call_llm_text", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            responder = AIResponder()
            session = AsyncMock()
            result = await responder.generate_response(
                session, sample_order, "kwork", ["Telegram-бот"]
            )
            assert result == mock_response
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_response_fallback_on_empty(self, sample_order):
        """При пустом ответе от LLM используется шаблон."""
        with patch("ai_router.call_llm_text", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""
            responder = AIResponder()
            session = AsyncMock()
            result = await responder.generate_response(
                session, sample_order, "kwork", []
            )
            assert len(result) > 0
            assert sample_order.title in result

    @pytest.mark.asyncio
    async def test_generate_response_fallback_on_exception(self, sample_order):
        """При ошибке LLM используется fallback-шаблон."""
        with patch("ai_router.call_llm_text", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM unavailable")
            responder = AIResponder()
            session = AsyncMock()
            result = await responder.generate_response(
                session, sample_order, "fl.ru", []
            )
            assert len(result) > 0
            assert sample_order.title in result

    @pytest.mark.asyncio
    async def test_generate_response_includes_platform_in_prompt(self, sample_order):
        """Промпт содержит название платформы."""
        with patch("ai_router.call_llm_text", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Test response"
            responder = AIResponder()
            session = AsyncMock()
            await responder.generate_response(
                session, sample_order, "kwork", []
            )
            # Проверяем что промпт содержит платформу
            call_args = mock_llm.call_args
            prompt = call_args[0][1]
            assert "kwork" in prompt


class TestPortfolio:
    """Тесты подбора релевантных работ из портфолио."""

    def test_select_relevant_telegram_order(self, sample_order):
        """Для заказа на Telegram-бот находятся релевантные работы."""
        results = select_relevant(sample_order, top_k=3)
        assert len(results) > 0
        # Должен найтись Telegram-бот из портфолио
        assert any("Telegram" in r or "telegram" in r.lower() for r in results)

    def test_select_relevant_crypto_order(self, crypto_order):
        """Для крипто-заказа находятся релевантные работы."""
        results = select_relevant(crypto_order, top_k=3)
        assert len(results) > 0
        assert any("крипто" in r.lower() or "crypto" in r.lower() for r in results)

    def test_select_relevant_no_match(self, no_match_order):
        """Для заказа без совпадений возвращается пустой список."""
        results = select_relevant(no_match_order, top_k=3)
        assert results == []

    def test_select_relevant_top_k_limit(self, sample_order):
        """Возвращает не более top_k элементов."""
        results = select_relevant(sample_order, top_k=1)
        assert len(results) <= 1

    def test_select_relevant_returns_strings(self, sample_order):
        """Все элементы результата - строки."""
        results = select_relevant(sample_order)
        for item in results:
            assert isinstance(item, str)
