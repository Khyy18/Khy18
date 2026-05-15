"""Тесты ядра arbitrage_engine: расчёт APR, cross-pairs, top-by-apr."""

import arbitrage_engine as ae


def _snap(exchange: str, symbol: str, rate: float, interval: float = 8.0):
    """Хелпер: создать FundingSnapshot с авто-расчётом APR."""
    apr = ae._to_apr(rate, interval)
    return ae.FundingSnapshot(
        exchange=exchange,
        symbol=symbol,
        funding_rate=rate,
        next_funding_ts=0,
        mark_price=100.0,
        interval_hours=interval,
        apr=apr,
        net_apr=apr,  # без fee_drag для простоты теста
        side_recommendation=ae._classify_side(rate),
    )


class TestApr:
    def test_positive_funding_8h(self):
        # 0.01% за 8ч = 0.01% × 3 раза в день × 365 = ~10.95%
        apr = ae._to_apr(0.0001, 8.0)
        assert 0.10 < apr < 0.12

    def test_negative_funding(self):
        apr = ae._to_apr(-0.0002, 8.0)
        assert apr < 0
        assert -0.25 < apr < -0.20

    def test_zero_interval_safe(self):
        # Защита от деления на ноль.
        assert ae._to_apr(0.001, 0.0) == 0.0


class TestClassify:
    def test_positive(self):
        assert ae._classify_side(0.001) == "SHORT_PERP"

    def test_negative(self):
        assert ae._classify_side(-0.001) == "LONG_PERP"

    def test_near_zero(self):
        assert ae._classify_side(0.0) == "FLAT"
        assert ae._classify_side(1e-7) == "FLAT"


class TestCrossExchangePairs:
    def test_no_pair_when_one_exchange(self):
        snapshots = {
            "bybit": [_snap("bybit", "BTCUSDT", 0.0001)],
        }
        pairs = ae.cross_exchange_pairs(snapshots, min_edge_apr=0.0)
        assert pairs == []

    def test_finds_carry_when_funding_diverges(self):
        # На bybit funding +0.01% (SHORT получает), на okx -0.01% (LONG получает).
        # LONG нога — okx (rate ниже), SHORT нога — bybit (rate выше).
        snapshots = {
            "bybit": [_snap("bybit", "BTCUSDT", 0.0001)],
            "okx":   [_snap("okx",   "BTCUSDT", -0.0001)],
        }
        pairs = ae.cross_exchange_pairs(snapshots, min_edge_apr=0.0)
        assert len(pairs) == 1
        p = pairs[0]
        assert p.symbol == "BTCUSDT"
        assert p.long_leg.exchange == "okx"
        assert p.short_leg.exchange == "bybit"
        # edge_apr должен быть положительным (carry в нашу пользу).
        assert p.edge_apr > 0

    def test_filters_by_min_edge(self):
        snapshots = {
            "bybit": [_snap("bybit", "BTCUSDT", 0.00001)],
            "okx":   [_snap("okx",   "BTCUSDT", -0.00001)],
        }
        # Edge микроскопический, фильтр 50% APR его отбросит.
        pairs = ae.cross_exchange_pairs(snapshots, min_edge_apr=0.50)
        assert pairs == []


class TestTopByApr:
    def test_filters_below_threshold(self):
        snapshots = {
            "bybit": [
                _snap("bybit", "BTCUSDT", 0.00001),  # APR ~1.1%
                _snap("bybit", "ETHUSDT", 0.001),    # APR ~109%
            ],
        }
        top = ae.top_by_apr(snapshots, limit=10, min_abs_apr=0.10)
        # BTC отфильтрован (APR 1% < 10%), ETH прошёл.
        symbols = [s.symbol for s in top]
        assert "ETHUSDT" in symbols
        assert "BTCUSDT" not in symbols

    def test_sorted_by_abs_apr_desc(self):
        snapshots = {
            "bybit": [
                _snap("bybit", "AAA", 0.0005),    # ~55% APR
                _snap("bybit", "BBB", -0.0015),   # ~-164% APR (по модулю больше)
                _snap("bybit", "CCC", 0.0001),    # ~11%
            ],
        }
        top = ae.top_by_apr(snapshots, limit=10, min_abs_apr=0.05)
        # Порядок: BBB > AAA > CCC по |APR|.
        assert [s.symbol for s in top] == ["BBB", "AAA", "CCC"]


class TestFormatters:
    def test_format_pct_with_true_minus(self):
        # Должен использовать U+2212, не дефис.
        assert "\u2212" in ae.format_pct(-0.0123)
        assert "-" not in ae.format_pct(-0.0123).replace("\u2212", "")

    def test_format_apr_positive_no_minus(self):
        result = ae.format_apr(0.234)
        assert "\u2212" not in result
        assert "23.40%" in result
