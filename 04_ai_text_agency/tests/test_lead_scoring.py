"""Тесты для модуля Lead Scoring."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


# --- Тесты scorer ---


@pytest.mark.asyncio
async def test_score_lead_with_llm():
    """LeadScorer.score_lead с мок-LLM возвращает оценку."""
    from freelance_automation.base import Order
    from lead_scoring.scorer import LeadScorer

    order = Order(
        id="test-001",
        title="Telegram bot development",
        description="Need a Telegram bot for e-commerce with payments integration",
        budget=50000.0,
        url="https://example.com/order/1",
    )

    mock_response = {"score": 85, "factors": {"budget": 22, "urgency": 10, "service_fit": 25, "description_quality": 20}}

    with patch("ai_router.call_llm_json", new_callable=AsyncMock, return_value=mock_response):
        scorer = LeadScorer()
        session = AsyncMock()
        result = await scorer.score_lead(session, order)

    assert result["score"] == 85
    assert "factors" in result
    assert result["factors"]["service_fit"] == 25


@pytest.mark.asyncio
async def test_score_lead_llm_failure_fallback():
    """LeadScorer falls back to heuristic scoring when LLM fails."""
    from freelance_automation.base import Order
    from lead_scoring.scorer import LeadScorer

    order = Order(
        id="test-002",
        title="Срочно нужен Telegram бот",
        description="Автоматизация работы с клиентами через бот, нужно быстро, есть ТЗ на 500 слов. " * 5,
        budget=25000.0,
        url="https://example.com/order/2",
    )

    with patch("ai_router.call_llm_json", new_callable=AsyncMock, return_value=None):
        scorer = LeadScorer()
        session = AsyncMock()
        result = await scorer.score_lead(session, order)

    assert 0 <= result["score"] <= 100
    assert "factors" in result
    # Should have urgency score (contains "срочно", "быстро")
    assert result["factors"]["urgency"] > 0
    # Should have fit score (contains "бот", "автоматизация")
    assert result["factors"]["service_fit"] > 0


@pytest.mark.asyncio
async def test_heuristic_score_budget():
    """Heuristic scoring: budget factor."""
    from freelance_automation.base import Order
    from lead_scoring.scorer import LeadScorer

    scorer = LeadScorer()

    # High budget
    order_high = Order(id="h1", title="Test", description="x" * 100, budget=100000.0, url="u")
    result_high = scorer._heuristic_score(order_high)

    # Low budget
    order_low = Order(id="l1", title="Test", description="x" * 100, budget=1000.0, url="u")
    result_low = scorer._heuristic_score(order_low)

    assert result_high["factors"]["budget"] > result_low["factors"]["budget"]


# --- Тесты models ---


@pytest.fixture
def lead_db(tmp_path):
    """Фикстура: временная БД для lead_scoring."""
    db_path = str(tmp_path / "test_leads.db")
    with patch("lead_scoring.models.DB_PATH", db_path):
        from lead_scoring import models
        models.init_db()
        yield db_path


def test_save_and_get_score(lead_db):
    """Сохранение и получение оценки лида."""
    with patch("lead_scoring.models.DB_PATH", lead_db):
        from lead_scoring import models

        models.save_score("order-1", tg_id=123, score=75, factors={"budget": 20, "urgency": 15})
        result = models.get_score("order-1")

        assert result is not None
        assert result["order_id"] == "order-1"
        assert result["score"] == 75
        assert result["tg_id"] == 123
        assert result["factors"]["budget"] == 20


def test_get_top_leads(lead_db):
    """Получение топ лидов по оценке."""
    with patch("lead_scoring.models.DB_PATH", lead_db):
        from lead_scoring import models

        models.save_score("o-1", tg_id=0, score=90, factors={})
        models.save_score("o-2", tg_id=0, score=50, factors={})
        models.save_score("o-3", tg_id=0, score=80, factors={})

        top = models.get_top_leads(limit=2, min_score=0)
        assert len(top) == 2
        assert top[0]["score"] == 90
        assert top[1]["score"] == 80


def test_get_scores_above(lead_db):
    """Получение лидов выше порога."""
    with patch("lead_scoring.models.DB_PATH", lead_db):
        from lead_scoring import models

        models.save_score("o-a", tg_id=0, score=85, factors={})
        models.save_score("o-b", tg_id=0, score=40, factors={})
        models.save_score("o-c", tg_id=0, score=70, factors={})

        above = models.get_scores_above(70)
        assert len(above) == 2
        assert all(r["score"] >= 70 for r in above)


# --- Тесты integration ---


@pytest.mark.asyncio
async def test_auto_score_new_order(lead_db):
    """auto_score_new_order оценивает и сохраняет."""
    with patch("lead_scoring.models.DB_PATH", lead_db):
        from freelance_automation.base import Order
        from lead_scoring.integration import auto_score_new_order

        order = Order(
            id="int-001",
            title="Bot development",
            description="Need a complex bot" * 10,
            budget=30000.0,
            url="https://example.com/order/int",
        )

        mock_response = {"score": 78, "factors": {"budget": 20}}
        with patch("ai_router.call_llm_json", new_callable=AsyncMock, return_value=mock_response):
            session = AsyncMock()
            score = await auto_score_new_order(session, order)

        assert score == 78

        from lead_scoring import models
        saved = models.get_score("int-001")
        assert saved is not None
        assert saved["score"] == 78
