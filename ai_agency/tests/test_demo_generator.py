"""Tests for demo_generator module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import demo_generator


@pytest.mark.asyncio
class TestDemoGenerator:
    """Tests for demo content and ad creative generation."""

    async def test_service_descriptions_defined(self):
        """SERVICE_DESCRIPTIONS has entries for core services."""
        assert "copywriting" in demo_generator.SERVICE_DESCRIPTIONS
        assert "rewrite" in demo_generator.SERVICE_DESCRIPTIONS
        assert "seo" in demo_generator.SERVICE_DESCRIPTIONS
        assert "translation" in demo_generator.SERVICE_DESCRIPTIONS

    async def test_generate_demo_for_service_success(self):
        """generate_demo_for_service returns demo text."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ZADANIE: Write post\nREZULTAT: Great post"

        with patch.object(demo_generator, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            with patch("demo_generator._get_openai_client", return_value=mock_client):
                result = await demo_generator.generate_demo_for_service("copywriting")
                assert result is not None
                assert "ZADANIE" in result or "REZULTAT" in result or len(result) > 0

    async def test_generate_demo_for_service_failure(self):
        """generate_demo_for_service returns None on error."""
        with patch.object(demo_generator, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            with patch("demo_generator._get_openai_client", return_value=mock_client):
                result = await demo_generator.generate_demo_for_service("copywriting")
                assert result is None

    async def test_generate_ad_creative_success(self):
        """generate_ad_creative returns dict with headline/description/cta."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"headline": "AI Copywriting", "description": "Best texts", "cta": "Try now"}'
        )

        with patch.object(demo_generator, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            with patch("demo_generator._get_openai_client", return_value=mock_client):
                result = await demo_generator.generate_ad_creative("copywriting")
                assert result is not None
                assert "headline" in result
                assert "description" in result
                assert "cta" in result

    async def test_generate_ad_creative_failure(self):
        """generate_ad_creative returns None on error."""
        with patch.object(demo_generator, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            with patch("demo_generator._get_openai_client", return_value=mock_client):
                result = await demo_generator.generate_ad_creative("copywriting")
                assert result is None

    async def test_select_best_cases(self, initialized_db):
        """select_best_cases returns list of high-rated orders."""
        import database
        await database.get_or_create_client(telegram_id=700, username="democlient")
        order_id = await database.create_order(
            client_id=700, service_type="copywriting", input_text="test", price=100.0
        )
        await database.update_order_status(order_id, "completed", output_text="result")
        await database.update_order_rating(order_id, 5)

        cases = await demo_generator.select_best_cases(limit=5)
        assert len(cases) >= 1
        assert cases[0]["rating"] >= 4
