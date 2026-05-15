"""Full 180-day MR strategy backtest with monthly breakdown."""
import asyncio
import aiohttp
import sys
import math

sys.path.insert(0, '.')
from datetime import datetime, timezone
from momentum_engine import calc_rsi, calc_atr
from regime_classifier import calc_adx


# ─── OKX Data Loading ──────────────────────────────────────────────────

def _symbol_to_okx(symbol: str) -> str:
    """BTCUSDT -> BTC-USDT-SWAP, ETHUSDT -> ETH-USDT-SWAP."""
    base = symbol.replace("USDT", "")
    return f"{base}-USDT-SWAP"


async def fetch_all_klines(session, symbol, interval, days):
    """Load candles from OKX history-candles endpoint.

    Paginates with 'after' parameter (earliest ts from previous batch).
    OKX returns newest first. Sort oldest first, deduplicate by ts.
    """
    url = "https://www.okx.com/api/v5/market/history-candles"
    inst_id = _symbol_to_okx(symbol)
    bar = f"{interval}m"

    interval_min = int(interval)
    candles_needed = (days * 24 * 60) // interval_min

    all_klines = []
    after = None
    requests_made = 0

    while len(all_klines) < candles_needed:
        params = {
            "instId": inst_id,
            "bar": bar,
            "limit": "100",
        }
        if after is not None:
            params["after"] = after

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    print(f"  [OKX] HTTP {resp.status}")
                    break
                data = await resp.json()
        except Exception as exc:
            print(f"  [OKX] Error: {exc}")
            break

        if data.get("code") != "0":
            print(f"  [OKX] API error: {data.get('msg')}")
            break

        raw_list = data.get("data") or []
        if not raw_list:
            break

        batch = []
        for k in raw_list:
            try:
                batch.append({
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            except (IndexError, TypeError, ValueError):
                continue

        if not batch:
            break

        all_klines.extend(batch)
        earliest_ts = min(k["ts"] for k in batch)
        after = str(earliest_ts)
        requests_made += 1

        await asyncio.sleep(0.2)

    # Sort oldest first
    all_klines.sort(key=lambda k: k["ts"])

    # Deduplicate by ts
    seen = set()
    unique = []
    for k in all_klines:
        if k["ts"] not in seen:
            seen.add(k["ts"])
            unique.append(k)

    print(f"  {symbol}: {requests_made} requests, {len(unique)} candles loaded")
    return unique[-candles_needed:] if len(unique) > candles_needed else unique


# ─── MR Backtest Engine ────────────────────────────────────────────────

def run_mr_backtest(klines, leverage=3):
    """Run the full MR strategy backtest.

    Strategy rules (from momentum_engine._process_symbol MR mode):
    - ADX < 25 (ranging regime)
    - Session filter: hour UTC 8-22
    - RSI < 25 -> LONG, RSI > 75 -> SHORT
    - RSI momentum filter: skip if delta too extreme
    - Break-even at +0.5%
    - Dynamic ATR SL: max(1.5%, ATR*1.5/price)
    - RSI exit: LONG exits RSI > 55, SHORT exits RSI < 45
    - Time stop: 20 bars
    - Fee: 0.00055 per side
    """
    if len(klines) < 51:
        return {'trades': [], 'equity_curve': [1.0], 'monthly': [],
                'total_pnl': 0.0, 'winrate': 0.0, 'max_dd': 0.0, 'sharpe': 0.0}

    fee_per_side = 0.00055
    fee_round_trip = fee_per_side * 2

    trades = []
    equity_curve = [1.0]
    daily_returns = []

    position = None  # {'side', 'entry', 'entry_bar', 'sl', 'be_moved'}

    bars_per_day = 96  # 15m bars in a day
    day_start_equity = 1.0
    bar_count_in_day = 0

    for i in range(50, len(klines)):
        bar = klines[i]
        price = bar["close"]
        high = bar["high"]
        low = bar["low"]

        # Track daily returns
        bar_count_in_day += 1
        if bar_count_in_day >= bars_per_day:
            daily_ret = (equity_curve[-1] - day_start_equity) / day_start_equity if day_start_equity > 0 else 0
            daily_returns.append(daily_ret)
            day_start_equity = equity_curve[-1]
            bar_count_in_day = 0

        # Compute indicators
        lookback_klines = klines[max(0, i - 49):i + 1]
        adx = calc_adx(lookback_klines, period=14)

        closes_30 = [klines[j]["close"] for j in range(max(0, i - 29), i + 1)]
        rsi = calc_rsi(closes_30, period=14)

        atr_klines = klines[max(0, i - 19):i + 1]
        atr = calc_atr(atr_klines, period=14)

        # Bar hour (UTC) from timestamp
        bar_hour = datetime.fromtimestamp(bar["ts"] / 1000, tz=timezone.utc).hour

        if position is not None:
            # Position management
            entry = position["entry"]
            side = position["side"]
            bars_held = i - position["entry_bar"]

            if side == "LONG":
                unrealized_pnl = (price - entry) / entry
            else:
                unrealized_pnl = (entry - price) / entry

            # Break-even: move SL to entry if unrealized >= +0.5%
            if not position["be_moved"] and unrealized_pnl >= 0.005:
                position["sl"] = entry
                position["be_moved"] = True

            # Check exits
            should_close = False
            reason = ""

            # SL hit (check with high/low)
            if side == "LONG" and low <= position["sl"]:
                should_close = True
                reason = "SL"
                # Exit at SL price
                price = position["sl"]
            elif side == "SHORT" and high >= position["sl"]:
                should_close = True
                reason = "SL"
                price = position["sl"]

            # RSI exit
            if not should_close:
                if side == "LONG" and rsi > 55:
                    should_close = True
                    reason = "RSI_EXIT"
                elif side == "SHORT" and rsi < 45:
                    should_close = True
                    reason = "RSI_EXIT"

            # Time stop: 20 bars
            if not should_close and bars_held >= 20:
                should_close = True
                reason = "TIME_STOP"

            if should_close:
                if side == "LONG":
                    raw_pnl = (price - entry) / entry
                else:
                    raw_pnl = (entry - price) / entry

                net_pnl = raw_pnl - fee_round_trip
                leveraged_pnl = net_pnl * leverage

                trades.append({
                    "side": side,
                    "entry": entry,
                    "exit": price,
                    "entry_bar": position["entry_bar"],
                    "exit_bar": i,
                    "bars_held": bars_held,
                    "pnl_pct": net_pnl,
                    "pnl_leveraged": leveraged_pnl,
                    "reason": reason,
                })

                new_eq = equity_curve[-1] * (1 + leveraged_pnl)
                equity_curve.append(max(new_eq, 0.0))
                position = None
            else:
                equity_curve.append(equity_curve[-1])
        else:
            # Entry logic
            # ADX < 25 (ranging regime)
            if adx >= 25:
                equity_curve.append(equity_curve[-1])
                continue

            # Session filter: 8-22 UTC
            if bar_hour < 8 or bar_hour >= 22:
                equity_curve.append(equity_curve[-1])
                continue

            # RSI signal
            signal = None
            if rsi < 25:
                signal = "LONG"
            elif rsi > 75:
                signal = "SHORT"

            if signal is None:
                equity_curve.append(equity_curve[-1])
                continue

            # RSI momentum filter
            closes_older = [klines[j]["close"] for j in range(max(0, i - 32), i - 2)]
            if len(closes_older) >= 15:
                rsi_older = calc_rsi(closes_older, period=14)
                delta = rsi - rsi_older
                if signal == "LONG" and delta < -20:
                    equity_curve.append(equity_curve[-1])
                    continue
                if signal == "SHORT" and delta > 20:
                    equity_curve.append(equity_curve[-1])
                    continue

            # Equity curve protection: skip entry if recent trades show losing streak
            # Mirrors the production guard in momentum_engine._process_symbol
            if len(trades) >= 5:
                recent_pnl = [t["pnl_pct"] for t in trades[-10:]]
                recent_3 = sum(recent_pnl[-3:])
                cumulative = sum(recent_pnl)
                if recent_3 < 0 and cumulative < 0:
                    equity_curve.append(equity_curve[-1])
                    continue

            # Dynamic ATR SL
            sl_pct = max(0.015, (atr / price) * 1.5) if price > 0 else 0.015

            if signal == "LONG":
                sl_price = price * (1 - sl_pct)
            else:
                sl_price = price * (1 + sl_pct)

            position = {
                "side": signal,
                "entry": price,
                "entry_bar": i,
                "sl": sl_price,
                "be_moved": False,
            }

            equity_curve.append(equity_curve[-1])

    # Close any open position at the end
    if position is not None:
        price = klines[-1]["close"]
        entry = position["entry"]
        side = position["side"]
        bars_held = len(klines) - 1 - position["entry_bar"]

        if side == "LONG":
            raw_pnl = (price - entry) / entry
        else:
            raw_pnl = (entry - price) / entry

        net_pnl = raw_pnl - fee_round_trip
        leveraged_pnl = net_pnl * leverage

        trades.append({
            "side": side,
            "entry": entry,
            "exit": price,
            "entry_bar": position["entry_bar"],
            "exit_bar": len(klines) - 1,
            "bars_held": bars_held,
            "pnl_pct": net_pnl,
            "pnl_leveraged": leveraged_pnl,
            "reason": "END",
        })

    # Compute statistics
    n_trades = len(trades)
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    winrate = wins / n_trades if n_trades > 0 else 0.0
    total_pnl = sum(t["pnl_leveraged"] for t in trades)

    # Max drawdown on equity curve
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualized from daily returns)
    # Add final partial day
    if bar_count_in_day > 0 and day_start_equity > 0:
        daily_ret = (equity_curve[-1] - day_start_equity) / day_start_equity
        daily_returns.append(daily_ret)

    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_ret = math.sqrt(variance) if variance > 0 else 0.0
        sharpe = (mean_ret / std_ret) * math.sqrt(365) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    # Monthly breakdown
    monthly = _compute_monthly(trades, klines, leverage)

    return {
        'trades': trades,
        'equity_curve': equity_curve,
        'monthly': monthly,
        'total_pnl': total_pnl,
        'winrate': winrate,
        'max_dd': max_dd,
        'sharpe': sharpe,
    }


def _compute_monthly(trades, klines, leverage):
    """Group trades by month and compute stats."""
    if not trades or not klines:
        return []

    months = {}
    for t in trades:
        # Use entry bar timestamp to determine month
        entry_ts = klines[t["entry_bar"]]["ts"]
        dt = datetime.fromtimestamp(entry_ts / 1000, tz=timezone.utc)
        month_key = dt.strftime("%Y-%m")

        if month_key not in months:
            months[month_key] = []
        months[month_key].append(t)

    monthly = []
    for month_key in sorted(months.keys()):
        month_trades = months[month_key]
        n = len(month_trades)
        wins = sum(1 for t in month_trades if t["pnl_pct"] > 0)
        wr = wins / n if n > 0 else 0.0
        pnl_pct = sum(t["pnl_leveraged"] for t in month_trades)

        # Max drawdown within month (simple: worst cumulative sequence)
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in month_trades:
            cumulative += t["pnl_leveraged"]
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        monthly.append({
            'month': month_key,
            'pnl_pct': pnl_pct,
            'trades': n,
            'winrate': wr,
            'max_dd': max_dd,
        })

    return monthly


# ─── Main ──────────────────────────────────────────────────────────────

async def main():
    """Load BTC and ETH 180 days 15m, run MR backtest, print results."""
    print("=== FULL MR BACKTEST (180 days) ===\n")

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        print("Loading BTC-USDT 15m candles...")
        btc_klines = await fetch_all_klines(session, "BTCUSDT", "15", 180)

        print("Loading ETH-USDT 15m candles...")
        eth_klines = await fetch_all_klines(session, "ETHUSDT", "15", 180)

    print(f"\nBTC: {len(btc_klines)} candles, ETH: {len(eth_klines)} candles\n")

    if len(btc_klines) < 100:
        print("ERROR: Not enough BTC data")
        return
    if len(eth_klines) < 100:
        print("ERROR: Not enough ETH data")
        return

    # Run backtests
    print("Running BTC backtest...")
    btc_result = run_mr_backtest(btc_klines, leverage=3)
    print("Running ETH backtest...")
    eth_result = run_mr_backtest(eth_klines, leverage=3)

    # Print results
    _print_symbol_results("BTC-USDT", btc_result)
    _print_symbol_results("ETH-USDT", eth_result)

    # Portfolio combined (equal weight)
    _print_portfolio(btc_result, eth_result)


def _print_symbol_results(name, result):
    """Print per-symbol monthly results table."""
    print(f"\n--- {name} Results ---")
    print(f"{'Month':<12}| {'PnL%':>7} | {'Trades':>6} | {'WR%':>5} | {'MaxDD%':>7}")
    print("-" * 50)

    for m in result['monthly']:
        pnl_str = f"{m['pnl_pct']*100:+.1f}%"
        wr_str = f"{m['winrate']*100:.0f}%"
        dd_str = f"{m['max_dd']*100:.1f}%"
        print(f"{m['month']:<12}| {pnl_str:>7} | {m['trades']:>6} | {wr_str:>5} | {dd_str:>7}")

    print("-" * 50)
    n_trades = len(result['trades'])
    total_str = f"{result['total_pnl']*100:+.1f}%"
    wr_str = f"{result['winrate']*100:.0f}%"
    dd_str = f"{result['max_dd']*100:.1f}%"
    print(f"{'TOTAL':<12}| {total_str:>7} | {n_trades:>6} | {wr_str:>5} | {dd_str:>7}")
    print(f"Sharpe: {result['sharpe']:.2f}")


def _print_portfolio(btc_result, eth_result):
    """Print combined portfolio metrics (equal weight)."""
    print("\n--- Portfolio (equal weight) ---")

    # Average PnL (50% allocation each)
    total_pnl = (btc_result['total_pnl'] + eth_result['total_pnl']) / 2.0
    # Max DD: take the worst of combined
    max_dd = max(btc_result['max_dd'], eth_result['max_dd'])
    # Average sharpe
    avg_sharpe = (btc_result['sharpe'] + eth_result['sharpe']) / 2.0

    total_trades = len(btc_result['trades']) + len(eth_result['trades'])
    all_trades = btc_result['trades'] + eth_result['trades']
    wins = sum(1 for t in all_trades if t["pnl_pct"] > 0)
    winrate = wins / total_trades if total_trades > 0 else 0.0

    print(f"Total PnL: {total_pnl*100:+.1f}%")
    print(f"Total Trades: {total_trades}")
    print(f"Winrate: {winrate*100:.0f}%")
    print(f"Sharpe: {avg_sharpe:.2f}")
    print(f"Max DD: {max_dd*100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
