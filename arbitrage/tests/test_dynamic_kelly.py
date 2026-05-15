"""Tests for DynamicKelly."""

from arbitrage.dynamic_kelly import DynamicKelly


class TestDynamicKelly:
    def test_no_drawdown_full_kelly(self) -> None:
        """Zero drawdown gives factor close to 1.0."""
        dk = DynamicKelly()
        state = {
            "hwm": 1000.0,
            "current_bankroll": 1000.0,
            "recent_pnls": [1.0] * 50,
            "losing_streak": 0,
        }
        factor = dk.get_reduction_factor(state)
        assert factor >= 0.95

    def test_max_drawdown_zero_kelly(self) -> None:
        """Drawdown at max (15%) gives factor 0.0."""
        dk = DynamicKelly(max_drawdown_pct=15.0)
        state = {
            "hwm": 1000.0,
            "current_bankroll": 850.0,  # 15% drawdown
            "recent_pnls": [1.0] * 50,
            "losing_streak": 0,
        }
        factor = dk.get_reduction_factor(state)
        assert factor == 0.0

    def test_losing_streak_reduces_factor(self) -> None:
        """Losing streak > 5 should reduce factor."""
        dk = DynamicKelly()
        base_state = {
            "hwm": 1000.0,
            "current_bankroll": 950.0,  # 5% drawdown
            "recent_pnls": [1.0] * 50,
            "losing_streak": 0,
        }
        streak_state = {
            "hwm": 1000.0,
            "current_bankroll": 950.0,
            "recent_pnls": [1.0] * 50,
            "losing_streak": 7,
        }
        base_factor = dk.get_reduction_factor(base_state)
        streak_factor = dk.get_reduction_factor(streak_state)
        assert streak_factor < base_factor

    def test_high_variance_reduces_factor(self) -> None:
        """High variance in recent PnLs should reduce factor."""
        dk = DynamicKelly()
        low_var_state = {
            "hwm": 1000.0,
            "current_bankroll": 980.0,
            "recent_pnls": [1.0] * 50,  # low variance
            "losing_streak": 0,
        }
        high_var_state = {
            "hwm": 1000.0,
            "current_bankroll": 980.0,
            "recent_pnls": [10.0, -10.0] * 25,  # high variance
            "losing_streak": 0,
        }
        low_factor = dk.get_reduction_factor(low_var_state)
        high_factor = dk.get_reduction_factor(high_var_state)
        assert high_factor < low_factor

    def test_factor_clamped_0_1(self) -> None:
        """Factor should always be between 0.0 and 1.0."""
        dk = DynamicKelly()
        # Extreme case
        state = {
            "hwm": 1000.0,
            "current_bankroll": 500.0,  # 50% drawdown > max
            "recent_pnls": [-100.0] * 50,
            "losing_streak": 20,
        }
        factor = dk.get_reduction_factor(state)
        assert 0.0 <= factor <= 1.0
