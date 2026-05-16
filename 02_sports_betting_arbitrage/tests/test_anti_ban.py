"""Tests for AntiBanEngine from arbitrage.anti_ban."""

from __future__ import annotations

import time

from arbitrage.anti_ban import AntiBanEngine


class TestCheckFrequency:
    """Tests for check_frequency method."""

    def test_check_frequency_allows(self) -> None:
        """Under limit returns True."""
        engine = AntiBanEngine(max_bets_per_hour=5)
        assert engine.check_frequency("bet365") is True

    def test_check_frequency_blocks(self) -> None:
        """Over limit returns False."""
        engine = AntiBanEngine(max_bets_per_hour=2)
        engine.record_bet("bet365")
        engine.record_bet("bet365")
        assert engine.check_frequency("bet365") is False


class TestCheckCorrelation:
    """Tests for check_correlation method."""

    def test_check_correlation_allows_first(self) -> None:
        """First bet on event passes."""
        engine = AntiBanEngine()
        assert engine.check_correlation("bet365", "event1") is True

    def test_check_correlation_blocks_repeat(self) -> None:
        """Immediate repeat on same event is blocked."""
        engine = AntiBanEngine()
        engine.check_correlation("bet365", "event1")  # first call records it
        assert engine.check_correlation("bet365", "event1") is False


class TestDetectPreBan:
    """Tests for detect_pre_ban method."""

    def test_detect_pre_ban_normal(self) -> None:
        """Normal acceptance times return (False, '')."""
        engine = AntiBanEngine()
        # Record consistent acceptance times
        for _ in range(5):
            engine.record_acceptance_time("bet365", 1.0)
        is_ban, msg = engine.detect_pre_ban("bet365")
        assert is_ban is False
        assert msg == ""

    def test_detect_pre_ban_elevated(self) -> None:
        """3 elevated acceptance times trigger detection."""
        engine = AntiBanEngine()
        # Baseline: normal times
        for _ in range(5):
            engine.record_acceptance_time("bet365", 1.0)
        # Last 3: elevated (> 2x baseline average of 1.0)
        for _ in range(3):
            engine.record_acceptance_time("bet365", 3.0)
        is_ban, msg = engine.detect_pre_ban("bet365")
        assert is_ban is True
        assert "bet365" in msg.lower() or "bet365" in msg


class TestHumanizeStake:
    """Tests for humanize_stake method."""

    def test_humanize_stake_within_bounds(self) -> None:
        """Result is within +/-15% of target."""
        engine = AntiBanEngine()
        target = 100.0
        for _ in range(20):
            result = engine.humanize_stake(target)
            assert 85.0 <= result <= 115.0


class TestGenerateNoiseBet:
    """Tests for generate_noise_bet method."""

    def test_generate_noise_bet_structure(self) -> None:
        """Returns valid dict with required keys."""
        engine = AntiBanEngine()
        noise = engine.generate_noise_bet()
        assert "event" in noise
        assert "sport" in noise
        assert "stake" in noise
        assert "odds" in noise
        assert "type" in noise
        assert noise["type"] == "noise"
        assert noise["stake"] > 0
        assert noise["odds"] > 1.0
