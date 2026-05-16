"""Tests for fraud_detector module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from freelance_automation.base import Order


@pytest.fixture(autouse=True)
def fraud_db(tmp_path, monkeypatch):
    """Use temp DB for fraud tests."""
    db_path = str(tmp_path / "test_fraud.db")
    monkeypatch.setenv("FRAUD_DB_PATH", db_path)
    # Patch the module-level DB_PATH
    monkeypatch.setattr("fraud_detector.models.DB_PATH", db_path)


def _make_order(**kwargs) -> Order:
    defaults = {
        "id": "test-001",
        "title": "Build a website",
        "description": "Need a simple landing page for my business.",
        "budget": 5000.0,
        "url": "https://example.com/order/1",
    }
    defaults.update(kwargs)
    return Order(**defaults)


class TestFraudDetector:
    """Tests for FraudDetector."""

    @pytest.mark.asyncio
    async def test_llm_returns_high_score(self):
        from fraud_detector.detector import FraudDetector

        detector = FraudDetector()
        order = _make_order(title="URGENT: Send money now!")

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 85, "flags": ["urgency_pressure", "scam_pattern"]}
            result = await detector.analyze_order(AsyncMock(), order)

        assert result["score"] == 85
        assert result["is_suspicious"] is True
        assert "urgency_pressure" in result["flags"]

    @pytest.mark.asyncio
    async def test_llm_returns_low_score(self):
        from fraud_detector.detector import FraudDetector

        detector = FraudDetector()
        order = _make_order()

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 10, "flags": []}
            result = await detector.analyze_order(AsyncMock(), order)

        assert result["score"] == 10
        assert result["is_suspicious"] is False
        assert result["flags"] == []

    @pytest.mark.asyncio
    async def test_heuristic_fallback_phone(self):
        from fraud_detector.detector import FraudDetector

        detector = FraudDetector()
        order = _make_order(
            description="Call me at +7 999 123 45 67 for details"
        )

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None  # LLM fails
            result = await detector.analyze_order(AsyncMock(), order)

        assert "phone_number_in_description" in result["flags"]
        assert result["score"] >= 25

    @pytest.mark.asyncio
    async def test_heuristic_fallback_email(self):
        from fraud_detector.detector import FraudDetector

        detector = FraudDetector()
        order = _make_order(
            description="Send your resume to hire@scam.com immediately"
        )

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None
            result = await detector.analyze_order(AsyncMock(), order)

        assert "email_in_description" in result["flags"]
        assert result["score"] >= 25

    @pytest.mark.asyncio
    async def test_heuristic_urgency(self):
        from fraud_detector.detector import FraudDetector

        detector = FraudDetector()
        order = _make_order(
            title="Срочно нужен разработчик",
            description="Нужно сделать сайт, очень срочно, за час."
        )

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None
            result = await detector.analyze_order(AsyncMock(), order)

        assert any("urgency" in f for f in result["flags"])

    @pytest.mark.asyncio
    async def test_heuristic_low_budget(self):
        from fraud_detector.detector import FraudDetector

        detector = FraudDetector()
        # Description with more than 50 words + budget < 100
        long_desc = " ".join(["word"] * 60)
        order = _make_order(
            budget=50.0,
            description=long_desc,
        )

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None
            result = await detector.analyze_order(AsyncMock(), order)

        assert "budget_too_low_for_complex_work" in result["flags"]


class TestFraudIntegration:
    """Tests for fraud filter integration."""

    @pytest.mark.asyncio
    async def test_filter_blocks_high_score(self):
        import fraud_detector.integration as integration_mod
        integration_mod._detector = None  # reset singleton

        from fraud_detector.integration import filter_before_response

        order = _make_order()

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 90, "flags": ["scam"]}
            result = await filter_before_response(AsyncMock(), order)

        assert result is False

    @pytest.mark.asyncio
    async def test_filter_allows_low_score(self):
        import fraud_detector.integration as integration_mod
        integration_mod._detector = None  # reset singleton

        from fraud_detector.integration import filter_before_response

        order = _make_order()

        with patch("ai_router.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"score": 20, "flags": []}
            result = await filter_before_response(AsyncMock(), order)

        assert result is True

    @pytest.mark.asyncio
    async def test_scheduler_calls_filter_when_enabled(self, monkeypatch, tmp_path):
        """Scheduler uses fraud filter when FRAUD_FILTER_ENABLED=true."""
        monkeypatch.setattr("config.FRAUD_FILTER_ENABLED", True)
        # Use a fresh dedup file so no orders are considered duplicates
        monkeypatch.setattr(
            "freelance_automation.scheduler.DEDUP_PATH",
            str(tmp_path / "dedup.json"),
        )

        from freelance_automation.base import FreelancePlatform
        from freelance_automation.scheduler import FreelanceScheduler

        mock_platform = AsyncMock(spec=FreelancePlatform)
        mock_platform.fetch_new_orders = AsyncMock(return_value=[
            _make_order(id="fraud-test-unique-001", title="Test Order"),
        ])
        mock_platform.respond_to_order = AsyncMock(return_value=True)

        scheduler = FreelanceScheduler(platforms=[mock_platform], keywords=[])

        with patch(
            "fraud_detector.integration.filter_before_response",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_filter:
            await scheduler.run_once()

        assert mock_filter.called
        assert mock_platform.respond_to_order.call_count == 1


class TestFraudModels:
    """Tests for fraud_detector.models."""

    def test_save_and_get_score(self):
        from fraud_detector.models import get_fraud_score, init_db, save_fraud_score

        init_db()
        save_fraud_score("order-1", 75, ["urgency", "phone"])
        result = get_fraud_score("order-1")

        assert result is not None
        assert result["score"] == 75
        assert "urgency" in result["flags"]

    def test_get_flagged_orders(self):
        from fraud_detector.models import get_flagged_orders, init_db, save_fraud_score

        init_db()
        save_fraud_score("safe-1", 20, [])
        save_fraud_score("suspicious-1", 80, ["scam"])
        save_fraud_score("suspicious-2", 90, ["phishing"])

        flagged = get_flagged_orders(min_score=70)
        assert len(flagged) == 2
        assert flagged[0]["score"] >= flagged[1]["score"]
