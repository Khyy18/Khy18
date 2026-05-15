"""Tests for service_discovery module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import service_discovery
import database


@pytest.mark.asyncio
class TestServiceDiscovery:
    """Tests for service discovery / trend monitoring module."""

    async def test_log_unrecognized_request(self, initialized_db):
        """log_unrecognized_request saves to database."""
        await database.get_or_create_client(telegram_id=200, username="seeker")
        await service_discovery.log_unrecognized_request(200, "I need video editing")

        requests = await service_discovery.get_unrecognized_requests(days=7)
        assert len(requests) >= 1
        assert requests[0]["text"] == "I need video editing"

    async def test_analyze_trends_no_trends(self, initialized_db):
        """analyze_trends returns empty when fewer than 5 similar."""
        await database.get_or_create_client(telegram_id=201, username="user201")
        # Only 2 requests - not enough for trend
        await service_discovery.log_unrecognized_request(201, "Need translation")
        await service_discovery.log_unrecognized_request(201, "Need a translator")

        trends = await service_discovery.analyze_trends(days=7)
        # Should not detect trend with only 2 requests
        translation_trends = [t for t in trends if t["category"] == "перевод"]
        assert len(translation_trends) == 0

    async def test_analyze_trends_detected(self, initialized_db):
        """analyze_trends detects trend when >5 similar requests."""
        await database.get_or_create_client(telegram_id=202, username="user202")
        # 6 requests for video category
        for i in range(6):
            await service_discovery.log_unrecognized_request(202, f"Need video editing #{i}")

        trends = await service_discovery.analyze_trends(days=7)
        video_trends = [t for t in trends if t["category"] == "видео"]
        assert len(video_trends) == 1
        assert video_trends[0]["count"] == 6

    async def test_suggest_service_prompt(self, initialized_db):
        """suggest_service_prompt generates a valid prompt."""
        samples = ["Need video editing", "Want to create a video", "Edit my clip"]
        prompt = service_discovery.suggest_service_prompt("video editing", samples)
        assert "video editing" in prompt
        assert "Need video editing" in prompt

    async def test_categorize_request(self, initialized_db):
        """_categorize_request correctly categorizes texts."""
        assert service_discovery._categorize_request("Need translation") == "перевод"
        assert service_discovery._categorize_request("Design a logo") == "дизайн"
        assert service_discovery._categorize_request("Write code for me") == "код"
        assert service_discovery._categorize_request("Something random") == "other"

    async def test_get_unrecognized_requests(self, initialized_db):
        """get_unrecognized_requests returns recent requests."""
        await database.get_or_create_client(telegram_id=203, username="user203")
        await service_discovery.log_unrecognized_request(203, "Custom request A")
        await service_discovery.log_unrecognized_request(203, "Custom request B")

        requests = await service_discovery.get_unrecognized_requests(days=7)
        texts = [r["text"] for r in requests]
        assert "Custom request A" in texts
        assert "Custom request B" in texts
