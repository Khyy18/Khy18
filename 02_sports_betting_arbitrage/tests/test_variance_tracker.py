"""Tests for VarianceTracker."""

from arbitrage.variance_tracker import VarianceTracker


class TestVarianceTracker:
    def test_update_and_get_variance(self) -> None:
        """After updates, variance should be non-negative."""
        vt = VarianceTracker(window_size=10)
        for i in range(10):
            vt.update(float(i))
        assert vt.get_variance() > 0

    def test_status_normal(self) -> None:
        """Low variance values should give 'normal' status."""
        vt = VarianceTracker(window_size=50)
        vt.set_historical_sigma(10.0)  # high threshold
        for i in range(50):
            vt.update(1.0)  # constant = zero variance
        assert vt.get_status() == "normal"

    def test_status_high_variance(self) -> None:
        """High variance values should give 'high' or 'critical' status."""
        vt = VarianceTracker(window_size=20)
        vt.set_historical_sigma(1.0)  # low threshold
        # Add highly variable data
        for i in range(20):
            vt.update(10.0 if i % 2 == 0 else -10.0)
        assert vt.get_status() in ("high", "critical")

    def test_should_reduce_kelly(self) -> None:
        """should_reduce_kelly returns True when status is high/critical."""
        vt = VarianceTracker(window_size=10)
        vt.set_historical_sigma(0.5)
        for i in range(10):
            vt.update(5.0 if i % 2 == 0 else -5.0)
        assert vt.should_reduce_kelly() is True

    def test_insufficient_data_normal(self) -> None:
        """With fewer than 5 values, status should be normal."""
        vt = VarianceTracker()
        vt.update(1.0)
        vt.update(2.0)
        assert vt.get_status() == "normal"
