"""Tests for pricing module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pricing import calculate_price


class TestCalculatePrice:
    """Test pricing.calculate_price() function."""

    def test_base_price_rewrite(self):
        """Base price for REWRITE service (100 RUB)."""
        price = calculate_price("rewrite", 500)
        assert price == 100.0

    def test_base_price_copywriting(self):
        """Base price for COPYWRITING service (150 RUB)."""
        price = calculate_price("copywriting", 500)
        assert price == 150.0

    def test_base_price_seo(self):
        """Base price for SEO service (200 RUB)."""
        price = calculate_price("seo", 500)
        assert price == 200.0

    def test_length_multiplier_under_1000(self):
        """Length <=1000 chars gives x1.0 multiplier."""
        price = calculate_price("rewrite", 1000)
        assert price == 100.0 * 1.0

    def test_length_multiplier_under_3000(self):
        """Length <=3000 chars gives x1.5 multiplier."""
        price = calculate_price("rewrite", 2000)
        assert price == 100.0 * 1.5

    def test_length_multiplier_under_5000(self):
        """Length <=5000 chars gives x2.0 multiplier."""
        price = calculate_price("rewrite", 4000)
        assert price == 100.0 * 2.0

    def test_length_multiplier_over_5000(self):
        """Length >5000 chars gives x3.0 multiplier."""
        price = calculate_price("rewrite", 6000)
        assert price == 100.0 * 3.0

    def test_urgency_multiplier(self):
        """Urgent flag gives x1.5 multiplier."""
        price = calculate_price("rewrite", 500, urgent=True)
        assert price == 100.0 * 1.5

    def test_combined_length_and_urgency(self):
        """Combined length (x1.5) + urgency (x1.5) multipliers."""
        price = calculate_price("rewrite", 2000, urgent=True)
        assert price == 100.0 * 1.5 * 1.5

    def test_invalid_service_type_returns_zero(self):
        """Invalid service_type returns 0.0."""
        price = calculate_price("nonexistent_service", 500)
        assert price == 0.0
