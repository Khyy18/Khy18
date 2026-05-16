"""Tests for memory functions from arbitrage.memory (use tmp db path)."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    """Set DB_PATH to a temp file for each test."""
    db_file = str(tmp_path / "test_arb.db")
    monkeypatch.setattr("arbitrage.memory.DB_PATH", db_file)
    # Also set env var in case _resolve_db_path is called again
    monkeypatch.setenv("ARB_DB_PATH", db_file)


class TestMemory:
    """Tests for arbitrage.memory module."""

    def test_init_db(self) -> None:
        """Creates tables without error."""
        from arbitrage import memory

        memory.init_db()
        # Calling again should be idempotent
        memory.init_db()

    def test_record_arb_returns_id(self) -> None:
        """record_arb returns integer id."""
        from arbitrage import memory

        memory.init_db()
        arb_id = memory.record_arb(
            sport="soccer_epl",
            event="Arsenal vs Chelsea",
            arb_type="surebet",
            bookmakers=["pinnacle", "bet365"],
            odds={"Home": 2.1, "Away": 3.5},
            profit_pct=2.5,
            edge_pct=0.0,
            ai_score=75,
        )
        assert isinstance(arb_id, int)
        assert arb_id > 0

    def test_record_bet_and_update(self) -> None:
        """record_bet + update_bet_result works correctly."""
        from arbitrage import memory

        memory.init_db()
        arb_id = memory.record_arb(
            sport="soccer_epl",
            event="Test Match",
            arb_type="surebet",
            bookmakers=["bk1"],
            odds={"H": 2.0},
            profit_pct=3.0,
            edge_pct=0.0,
        )
        bet_id = memory.record_bet(
            arb_id=arb_id,
            bookmaker="bk1",
            event="Test Match",
            outcome="Home",
            stake=50.0,
            odds=2.0,
        )
        assert isinstance(bet_id, int)
        assert bet_id > 0

        # Update result
        memory.update_bet_result(bet_id, "WON", 50.0)

        # Verify via get_stats
        stats = memory.get_stats()
        assert stats["won_bets"] == 1
        assert stats["total_pnl"] == 50.0

    def test_get_stats(self) -> None:
        """get_stats returns correct counts."""
        from arbitrage import memory

        memory.init_db()
        stats = memory.get_stats()
        assert "total_arbs" in stats
        assert "total_bets" in stats
        assert "won_bets" in stats
        assert "total_pnl" in stats
        assert stats["total_arbs"] == 0
        assert stats["total_bets"] == 0

    def test_bankroll_state(self) -> None:
        """save_bankroll_state and load_bankroll_state work together."""
        from arbitrage import memory

        memory.init_db()
        memory.save_bankroll_state(5000.0)
        loaded = memory.load_bankroll_state()
        assert loaded == 5000.0
