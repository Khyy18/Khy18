"""Tests for autopilot features: auto-respond leads, ad autopilot, auto-moderate."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import config
import database
import lead_parser
import ad_manager
import reviews


@pytest.mark.asyncio
class TestAutoRespondLeads:
    """Tests for lead_parser auto-respond mode."""

    async def test_generate_response_fallback(self, initialized_db):
        """generate_response returns template when OpenAI unavailable."""
        order = {"title": "SEO-текст для сайта", "description": "Нужен SEO-текст"}
        response = await lead_parser.generate_response(order, "SEO")
        assert "SEO-текст для сайта" in response
        assert len(response) > 50

    async def test_generate_response_with_description(self, initialized_db):
        """generate_response includes order title in fallback."""
        order = {
            "title": "Рерайт статьи",
            "description": "Нужен рерайт статьи о маркетинге, 3000 слов",
        }
        response = await lead_parser.generate_response(order, "рерайт")
        assert "Рерайт статьи" in response

    async def test_auto_respond_config_default(self, initialized_db):
        """AUTO_RESPOND_LEADS defaults to False."""
        assert config.AUTO_RESPOND_LEADS is False


@pytest.mark.asyncio
class TestAdAutopilot:
    """Tests for ad_manager autopilot mode."""

    async def test_calculate_ad_budget_no_revenue(self, initialized_db):
        """calculate_ad_budget returns 0 when no revenue."""
        budget = await ad_manager.calculate_ad_budget(7)
        assert budget == 0.0

    async def test_calculate_ad_budget_with_revenue(self, initialized_db):
        """calculate_ad_budget returns 30% of revenue."""
        await database.get_or_create_client(telegram_id=900, username="aduser")
        o1 = await database.create_order(
            client_id=900, service_type="rewrite", input_text="t", price=10000.0
        )
        await database.update_order_status(o1, "completed", "result")

        budget = await ad_manager.calculate_ad_budget(7)
        assert budget == 3000.0  # 30% of 10000

    async def test_get_best_roi_channels_empty(self, initialized_db):
        """get_best_roi_channels returns empty list when no campaigns."""
        channels = await ad_manager.get_best_roi_channels()
        assert channels == []

    async def test_recommend_channels_budget(self, initialized_db):
        """recommend_channels returns channels based on budget."""
        channels = await ad_manager.recommend_channels("seo", 3000)
        assert len(channels) >= 2  # 1000+ and 2000+ thresholds

    async def test_ad_autopilot_config_default(self, initialized_db):
        """AD_AUTOPILOT defaults to False."""
        assert config.AD_AUTOPILOT is False

    async def test_create_ad_campaign(self, initialized_db):
        """create_ad_campaign saves campaign to DB."""
        campaign_id = await ad_manager.create_ad_campaign("@test_channel", 5000.0)
        assert campaign_id is not None
        assert campaign_id > 0


@pytest.mark.asyncio
class TestAutoModerateReviews:
    """Tests for reviews auto-moderation mode."""

    async def test_auto_moderate_short_text(self, initialized_db):
        """auto_moderate rejects text shorter than 10 chars."""
        assert reviews.auto_moderate("Short") is False
        assert reviews.auto_moderate("Ok") is False
        assert reviews.auto_moderate("123456789") is False  # 9 chars

    async def test_auto_moderate_valid_length(self, initialized_db):
        """auto_moderate accepts text with 10+ chars."""
        assert reviews.auto_moderate("1234567890") is True  # exactly 10
        assert reviews.auto_moderate("Good service here") is True

    async def test_auto_approve_clean_review(self, initialized_db):
        """Clean review is auto-approved when AUTO_MODERATE_REVIEWS=True."""
        config.AUTO_MODERATE_REVIEWS = True
        await database.get_or_create_client(telegram_id=1000, username="auto")
        order_id = await database.create_order(
            client_id=1000, service_type="rewrite", input_text="t", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=1000, order_id=order_id, text="Amazing quality work!", rating=5
        )
        assert review_id is not None

        approved = await reviews.get_approved_reviews(limit=10)
        assert any(r["id"] == review_id for r in approved)

    async def test_profane_review_goes_to_pending(self, initialized_db):
        """Profane review goes to pending for manual moderation."""
        config.AUTO_MODERATE_REVIEWS = True
        await database.get_or_create_client(telegram_id=1001, username="profane")
        order_id = await database.create_order(
            client_id=1001, service_type="rewrite", input_text="t", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=1001, order_id=order_id, text="This is total shit service", rating=1
        )
        assert review_id is not None

        pending = await reviews.get_pending_reviews()
        assert any(r["id"] == review_id for r in pending)

    async def test_auto_moderate_config_default(self, initialized_db):
        """AUTO_MODERATE_REVIEWS defaults to True."""
        assert config.AUTO_MODERATE_REVIEWS is True
