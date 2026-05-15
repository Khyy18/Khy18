"""Tests for ad_copywriter module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
class TestAdCopywriter:
    """Test ad_copywriter module functionality."""

    async def test_generate_fallback_returns_3_variants(self, initialized_db):
        """Fallback generation returns exactly 3 variants."""
        import ad_copywriter

        # Force fallback by mocking _get_client to return None
        with patch.object(ad_copywriter, "_get_client", return_value=None):
            variants = await ad_copywriter.generate_ad_copy("coffee", 5000, "informal")
            assert len(variants) == 3

    async def test_variant_structure(self, initialized_db):
        """Each variant has required keys."""
        import ad_copywriter

        with patch.object(ad_copywriter, "_get_client", return_value=None):
            variants = await ad_copywriter.generate_ad_copy("tech", 10000, "formal")
            for v in variants:
                assert "variant" in v
                assert "text" in v
                assert "utm_link" in v
                assert "length_type" in v

    async def test_utm_link_generation(self, initialized_db):
        """UTM links are properly formatted."""
        import ad_copywriter
        link = ad_copywriter.generate_utm_link("test123", "short")
        assert "t.me/" in link
        assert "ad_" in link
        assert "short" in link

    async def test_length_types_included(self, initialized_db):
        """All 3 variants have different length types."""
        import ad_copywriter

        with patch.object(ad_copywriter, "_get_client", return_value=None):
            variants = await ad_copywriter.generate_ad_copy("beauty", 3000, "informal")
            length_types = [v["length_type"] for v in variants]
            assert "short" in length_types
            assert "medium" in length_types
            assert "long" in length_types

    async def test_campaign_id_generation(self, initialized_db):
        """_generate_campaign_id returns consistent hash."""
        import ad_copywriter
        id1 = ad_copywriter._generate_campaign_id("niche1", "formal")
        id2 = ad_copywriter._generate_campaign_id("niche1", "formal")
        id3 = ad_copywriter._generate_campaign_id("niche2", "formal")
        assert id1 == id2
        assert id1 != id3
        assert len(id1) == 8
