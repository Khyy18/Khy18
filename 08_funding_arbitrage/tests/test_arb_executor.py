"""Тесты ключевых функций arb_executor: scoring, leg cap, candidate selection."""

from unittest.mock import MagicMock

import pytest

import arb_executor as ae
import arbitrage_engine as engine


def _make_pair(symbol, long_ex, short_ex, edge_apr, next_funding_ts=0):
    long_leg = engine.FundingSnapshot(
        exchange=long_ex, symbol=symbol,
        funding_rate=-0.0001, next_funding_ts=next_funding_ts,
        mark_price=100.0, interval_hours=8.0,
        apr=-0.10, net_apr=-0.11, side_recommendation="LONG_PERP",
    )
    short_leg = engine.FundingSnapshot(
        exchange=short_ex, symbol=symbol,
        funding_rate=0.0001, next_funding_ts=next_funding_ts,
        mark_price=100.05, interval_hours=8.0,
        apr=0.10, net_apr=0.09, side_recommendation="SHORT_PERP",
    )
    return engine.CrossPair(
        symbol=symbol, long_leg=long_leg, short_leg=short_leg,
        edge_apr=edge_apr, net_edge_apr=edge_apr - 0.01,
    )


class TestPerExchangeLegCount:
    def test_empty_positions(self):
        assert ae._per_exchange_leg_count([]) == {}

    def test_counts_both_legs(self):
        positions = [
            {"long_exchange": "bybit", "short_exchange": "okx"},
            {"long_exchange": "okx",   "short_exchange": "binance"},
        ]
        counts = ae._per_exchange_leg_count(positions)
        assert counts == {"bybit": 1, "okx": 2, "binance": 1}

    def test_normalizes_to_lower(self):
        positions = [{"long_exchange": "BYBIT", "short_exchange": "OKX"}]
        counts = ae._per_exchange_leg_count(positions)
        assert "bybit" in counts and "okx" in counts


class TestPreFundingBonus:
    def test_neutral_when_far_from_funding(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ARB_PREFUNDING_BONUS_WINDOW_MIN", 30, raising=False)
        # Funding через 4 часа = 14400000 ms. Должен быть 1.0 (нейтрально).
        import time
        future = int(time.time() * 1000) + 4 * 3600 * 1000
        cand = _make_pair("BTC", "okx", "bybit", 0.20, next_funding_ts=future)
        bonus = ae._pre_funding_bonus(cand)
        assert 0.95 <= bonus <= 1.05

    def test_bonus_when_funding_imminent(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ARB_PREFUNDING_BONUS_WINDOW_MIN", 30, raising=False)
        # Funding через 5 минут — должен быть бонус.
        import time
        future = int(time.time() * 1000) + 5 * 60 * 1000
        cand = _make_pair("BTC", "okx", "bybit", 0.20, next_funding_ts=future)
        bonus = ae._pre_funding_bonus(cand)
        assert bonus > 1.2  # существенный бонус

    def test_no_bonus_when_window_zero(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ARB_PREFUNDING_BONUS_WINDOW_MIN", 0, raising=False)
        cand = _make_pair("BTC", "okx", "bybit", 0.20, next_funding_ts=999)
        assert ae._pre_funding_bonus(cand) == 1.0

    def test_no_next_ts_returns_neutral(self):
        cand = _make_pair("BTC", "okx", "bybit", 0.20, next_funding_ts=0)
        assert ae._pre_funding_bonus(cand) == 1.0


class TestSelectCandidates:
    def test_excludes_used_symbols(self, monkeypatch):
        # Мокаем cross_exchange_pairs.
        cand1 = _make_pair("BTCUSDT", "okx", "bybit", 0.30)
        cand2 = _make_pair("ETHUSDT", "okx", "bybit", 0.25)
        monkeypatch.setattr(
            engine, "cross_exchange_pairs",
            lambda *args, **kwargs: [cand1, cand2],
        )
        result = ae._select_candidates(
            snapshots={}, min_net_apr=0.10,
            excluded_symbols={"BTCUSDT"},
        )
        assert len(result) == 1
        assert result[0].symbol == "ETHUSDT"

    def test_filters_by_allowed(self, monkeypatch):
        cand1 = _make_pair("BTCUSDT", "okx", "bybit", 0.30)
        cand2 = _make_pair("DOGE", "okx", "bybit", 0.40)
        monkeypatch.setattr(
            engine, "cross_exchange_pairs",
            lambda *args, **kwargs: [cand1, cand2],
        )
        result = ae._select_candidates(
            snapshots={}, min_net_apr=0.10,
            allowed_symbols=["BTCUSDT"],
        )
        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"

    def test_returns_sorted_by_score(self, monkeypatch):
        # Без pre-funding бонуса — порядок по net_edge_apr (но мы передаём
        # уже отсортированный список — проверяем что limit работает).
        cands = [
            _make_pair(f"SYM{i}", "okx", "bybit", 0.50 - 0.01 * i)
            for i in range(8)
        ]
        monkeypatch.setattr(
            engine, "cross_exchange_pairs",
            lambda *args, **kwargs: cands,
        )
        result = ae._select_candidates(
            snapshots={}, min_net_apr=0.0, limit=3,
        )
        assert len(result) == 3
