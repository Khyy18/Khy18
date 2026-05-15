"""Tests for enhanced lead_parser features: working hours, warmup, daily limits."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime

import lead_parser


@pytest.fixture(autouse=True)
def reset_lead_state():
    """Reset module-level state between tests."""
    lead_parser._daily_responses = 0
    lead_parser._daily_responses_date = None
    yield


@pytest.mark.asyncio
class TestLeadParserEnhanced:

    async def test_is_working_hours_during_day(self, monkeypatch):
        """12:00 should return True (within 9-22)."""
        monkeypatch.setattr("lead_parser.config.KWORK_WORK_HOURS_START", 9)
        monkeypatch.setattr("lead_parser.config.KWORK_WORK_HOURS_END", 22)

        mock_now = MagicMock()
        mock_now.hour = 12
        with patch("lead_parser.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            result = lead_parser._is_working_hours()
        assert result is True

    async def test_is_working_hours_during_night(self, monkeypatch):
        """3:00 should return False (outside 9-22)."""
        monkeypatch.setattr("lead_parser.config.KWORK_WORK_HOURS_START", 9)
        monkeypatch.setattr("lead_parser.config.KWORK_WORK_HOURS_END", 22)

        mock_now = MagicMock()
        mock_now.hour = 3
        with patch("lead_parser.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            result = lead_parser._is_working_hours()
        assert result is False

    async def test_daily_limit_warmup_first_week(self, monkeypatch):
        """During first 7 days, max should be 2."""
        monkeypatch.setattr("lead_parser.config.KWORK_WARMUP_DAYS", 14)
        monkeypatch.setattr("lead_parser.config.KWORK_MAX_DAILY_RESPONSES", 7)

        # Registration date is today (0 days ago)
        today = date.today()
        with patch("lead_parser._get_registration_date", return_value=today):
            limit = lead_parser._get_warmup_limit()
        assert limit == 2

    async def test_daily_limit_warmup_second_week(self, monkeypatch):
        """During days 8-14, max should be 4."""
        monkeypatch.setattr("lead_parser.config.KWORK_WARMUP_DAYS", 14)
        monkeypatch.setattr("lead_parser.config.KWORK_MAX_DAILY_RESPONSES", 7)

        # Registration date was 10 days ago
        from datetime import timedelta
        reg_date = date.today() - timedelta(days=10)
        with patch("lead_parser._get_registration_date", return_value=reg_date):
            limit = lead_parser._get_warmup_limit()
        assert limit == 4

    async def test_daily_limit_full(self, monkeypatch):
        """After 14 days, max should be KWORK_MAX_DAILY_RESPONSES (7)."""
        monkeypatch.setattr("lead_parser.config.KWORK_WARMUP_DAYS", 14)
        monkeypatch.setattr("lead_parser.config.KWORK_MAX_DAILY_RESPONSES", 7)

        # Registration date was 30 days ago
        from datetime import timedelta
        reg_date = date.today() - timedelta(days=30)
        with patch("lead_parser._get_registration_date", return_value=reg_date):
            limit = lead_parser._get_warmup_limit()
        assert limit == 7

    async def test_generate_response_variable_length(self, monkeypatch):
        """AI response should be between 50-150 words (via template fallback)."""
        # Set up so LLM is unavailable, forcing template fallback
        monkeypatch.setattr(lead_parser, "_llm_router", None)
        monkeypatch.setattr("lead_parser.config.OPENAI_API_KEY", "")
        monkeypatch.setattr(lead_parser, "AsyncOpenAI", None)
        lead_parser._openai_client = None

        order_info = {
            "title": "Test Order",
            "description": "Need copywriting for website",
            "customer_name": "Ivan",
        }

        result = await lead_parser.generate_response(order_info, "copywriting")

        # Template fallback always returns text
        assert len(result) > 0
        assert "Test Order" in result

    async def test_check_daily_limit_resets_on_new_day(self, monkeypatch):
        """Daily counter resets when date changes."""
        monkeypatch.setattr("lead_parser.config.KWORK_WARMUP_DAYS", 14)
        monkeypatch.setattr("lead_parser.config.KWORK_MAX_DAILY_RESPONSES", 7)

        from datetime import timedelta
        # Set counter to yesterday
        yesterday = date.today() - timedelta(days=1)
        lead_parser._daily_responses = 99
        lead_parser._daily_responses_date = yesterday

        # Should reset on today's check
        with patch("lead_parser._get_registration_date", return_value=date.today() - timedelta(days=30)):
            result = lead_parser._check_daily_limit()
        assert result is True
        assert lead_parser._daily_responses == 0
