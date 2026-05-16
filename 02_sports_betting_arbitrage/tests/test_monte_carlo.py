"""Tests for MonteCarloSimulator."""

from arbitrage.monte_carlo import MonteCarloSimulator


class TestMonteCarloSimulator:
    def test_simulate_returns_result(self) -> None:
        """Simulate should return a SimulationResult with all fields."""
        sim = MonteCarloSimulator(win_rate=0.55, avg_profit_pct=2.5, avg_loss_pct=1.0)
        result = sim.simulate(1000.0, days=10, scenarios=100)
        assert result.scenarios_count == 100
        assert isinstance(result.median_pnl, float)
        assert isinstance(result.prob_ruin, float)
        assert isinstance(result.max_drawdown_pct, float)

    def test_simulate_prob_ruin_bounded(self) -> None:
        """Probability of ruin should be between 0 and 1."""
        sim = MonteCarloSimulator(win_rate=0.55, avg_profit_pct=2.5, avg_loss_pct=1.0)
        result = sim.simulate(1000.0, days=30, scenarios=200)
        assert 0.0 <= result.prob_ruin <= 1.0

    def test_estimate_kelly_reduction_at_zero_drawdown(self) -> None:
        """Zero drawdown should give factor 1.0 (full Kelly)."""
        sim = MonteCarloSimulator()
        factor = sim.estimate_kelly_reduction(0.0)
        assert factor == 1.0

    def test_estimate_kelly_reduction_at_max_drawdown(self) -> None:
        """Max drawdown (15%) should give factor 0.0."""
        sim = MonteCarloSimulator()
        factor = sim.estimate_kelly_reduction(15.0)
        assert factor == 0.0

    def test_percentiles_ordered(self) -> None:
        """p5 <= p25 <= median <= p75 <= p95."""
        sim = MonteCarloSimulator(win_rate=0.55, avg_profit_pct=2.5, avg_loss_pct=1.0)
        result = sim.simulate(1000.0, days=30, scenarios=500)
        assert result.p5_pnl <= result.p25_pnl
        assert result.p25_pnl <= result.median_pnl
        assert result.median_pnl <= result.p75_pnl
        assert result.p75_pnl <= result.p95_pnl
