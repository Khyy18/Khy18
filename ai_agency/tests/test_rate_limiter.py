"""Tests for rate_limiter module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from unittest.mock import patch

from rate_limiter import RateLimiter


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_first_order_allowed(self):
        """First order for a user is allowed."""
        limiter = RateLimiter()
        allowed, msg = limiter.check_rate_limit(1)
        assert allowed is True
        assert msg == ""

    def test_five_orders_in_hour_triggers_limit(self):
        """5 orders in an hour triggers the order limit."""
        limiter = RateLimiter()
        # Record 5 orders with timestamps in the past (beyond cooldown)
        base_time = time.time() - 3600 + 100  # within an hour but cooldown expired
        for i in range(5):
            limiter._orders[1].append(base_time + i * 60)

        # Now the order limit should be triggered
        allowed, msg = limiter.check_rate_limit(1)
        assert allowed is False
        assert "5 заказов" in msg

    def test_sixth_order_rejected(self):
        """6th order in an hour is rejected."""
        limiter = RateLimiter()
        # Record 5 orders (the limit)
        for _ in range(5):
            limiter.record_order(1)

        # 6th should be rejected
        allowed, msg = limiter.check_rate_limit(1)
        assert allowed is False

    def test_flood_detection_bans_user(self):
        """More than 20 messages in a minute bans user."""
        limiter = RateLimiter()
        # Record 21 messages quickly
        for _ in range(21):
            limiter.record_message(1)

        allowed, msg = limiter.check_rate_limit(1)
        assert allowed is False
        assert "заблокированы" in msg or "Слишком" in msg

    def test_cooldown_between_orders(self):
        """30s cooldown is enforced between orders."""
        limiter = RateLimiter()
        limiter.record_order(1)

        # Immediately after an order, cooldown should be active
        cooldown = limiter.get_cooldown_remaining(1)
        assert cooldown > 0
        assert cooldown <= 30.0

        # check_rate_limit should reject due to cooldown
        allowed, msg = limiter.check_rate_limit(1)
        assert allowed is False
        assert "Подождите" in msg
