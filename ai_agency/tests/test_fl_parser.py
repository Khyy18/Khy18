"""Tests for FL.ru parser module: HTTP parsing, daily limits, working hours."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import fl_parser


@pytest.fixture(autouse=True)
def reset_fl_state():
    """Reset module-level state between tests."""
    fl_parser._daily_responses = 0
    fl_parser._daily_responses_date = None
    yield


@pytest.mark.asyncio
class TestFlParser:

    async def test_parse_fl_orders_extracts_entries(self):
        """parse_fl_orders extracts project entries from mocked HTML."""
        sample_html = """
        <div>
            <a href="/projects/12345/some-project">link</a>
            <div class="b-post__title"><a href="/x">Test Project Title</a></div>
            <div class="b-post__body">Project description text here</div>
        </div>
        """

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=sample_html)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                entries = await fl_parser.parse_fl_orders(["копирайтинг"])

        assert len(entries) >= 1
        assert entries[0]["id"] == "/projects/12345/some-project"
        assert "fl.ru" in entries[0]["link"]

    async def test_daily_limit_blocks_excess_responses(self, monkeypatch):
        """_check_daily_limit returns False after hitting the limit."""
        monkeypatch.setattr("fl_parser.config.FL_MAX_DAILY_RESPONSES", 3)

        # Initially should pass
        assert fl_parser._check_daily_limit() is True

        # Simulate reaching limit
        fl_parser._daily_responses = 3
        from datetime import date
        fl_parser._daily_responses_date = date.today()

        assert fl_parser._check_daily_limit() is False

    async def test_working_hours_check(self, monkeypatch):
        """_is_working_hours returns correct values for different times."""
        monkeypatch.setattr("fl_parser.config.KWORK_WORK_HOURS_START", 9)
        monkeypatch.setattr("fl_parser.config.KWORK_WORK_HOURS_END", 22)

        # During working hours (12:00)
        mock_dt_day = MagicMock()
        mock_dt_day.hour = 12
        with patch("fl_parser.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt_day
            assert fl_parser._is_working_hours() is True

        # Outside working hours (3:00)
        mock_dt_night = MagicMock()
        mock_dt_night.hour = 3
        with patch("fl_parser.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt_night
            assert fl_parser._is_working_hours() is False

    async def test_increment_daily_counter(self):
        """_increment_daily_counter increases the response count."""
        assert fl_parser._daily_responses == 0
        fl_parser._increment_daily_counter()
        assert fl_parser._daily_responses == 1
        fl_parser._increment_daily_counter()
        assert fl_parser._daily_responses == 2
