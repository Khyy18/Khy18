"""Walk-forward оптимизатор параметров funding-арбитража.

Самостоятельный CLI-скрипт. Не запускается из main.py. Назначение —
по накопленной истории funding_snapshots подобрать оптимальные пороги
для входа/выхода и максимальное время удержания пары.

Запуск:
    python3 optimize.py --days 30 --min-trades 20
    python3 optimize.py --days 30 --save-best .env.optimized

Метод: brute-force по grid из (open_threshold, close_threshold,
max_hold_hours). Для каждой комбинации полностью реконструируется
торговля по истории и считаются метрики (n_trades, pnl, sharpe-proxy,
max_drawdown). Результаты сортируются по sharpe_proxy и выводятся
топ-N в консоль.

Не делает реальных сетевых вызовов — только SQLite. Полностью
детерминированный: одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
import memory


# --- Сетка параметров для перебора ----------------------------------

OPEN_THRESHOLDS: tuple[float, ...] = (0.10, 0.15, 0.20, 0.25, 0.30)
CLOSE_THRESHOLDS: tuple[float, ...] = (0.02, 0.05, 0.08, 0.10)
MAX_HOLD_HOURS_GRID: tuple[float, ...] = (48.0, 96.0, 168.0, 240.0)


# --- Структуры данных -----------------------------------------------

@dataclass
class _Snap:
    """Один снимок funding по (биржа, символ) на конкретный момент."""

    exchange: str
    symbol: str
    ts: datetime
    rate: float
    apr: float
    mark_price: float
    interval_hours: float


@dataclass
class _Trade:
    """Завершённая сделка (открыта и закрыта в симуляции)."""

    symbol: str
    long_ex: str
    short_ex: str
    open_ts: datetime
    close_ts: datetime
    held_hours: float
    funding_received: float
    fees: float
    pnl: float


@dataclass
class _ComboResult:
    """Метрики одного набора параметров на пройденной истории."""

    open_thr: float
    close_thr: float
    max_hold_h: float
    n_trades: int
    total_pnl: float
    mean_pnl: float
    win_rate: float
    sharpe_proxy: float
    max_drawdown: float


# --- Загрузка истории ------------------------------------------------

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_ts(s: str) -> datetime:
    """Преобразовать ISO-строку в aware-datetime в UTC."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_snapshots(
    db_path: str,
    days: int,
    symbols_filter: Optional[set[str]] = None,
) -> list[_Snap]:
    """Загрузить все снимки за последние `days` суток. Сортировка по ts."""
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )
    try:
        with _connect(db_path) as conn:
            # Проверим, существует ли таблица — на свежей БД её ещё нет.
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='funding_snapshots'"
            ).fetchone()
            if not row:
                return []
            rows = conn.execute(
                "SELECT exchange, symbol, ts, rate, apr, mark_price, interval_hours "
                "FROM funding_snapshots WHERE ts >= ? ORDER BY ts ASC, id ASC",
                (cutoff,),
            ).fetchall()
    except sqlite3.Error as exc:
        print(f"[OPTIMIZE] Ошибка чтения БД: {exc}", file=sys.stderr)
        return []

    out: list[_Snap] = []
    for r in rows:
        try:
            sym = str(r["symbol"])
            if symbols_filter and sym not in symbols_filter:
                continue
            interval = float(r["interval_hours"] or 8.0) or 8.0
            out.append(
                _Snap(
                    exchange=str(r["exchange"]).lower(),
                    symbol=sym,
                    ts=_parse_ts(str(r["ts"])),
                    rate=float(r["rate"] or 0.0),
                    apr=float(r["apr"] or 0.0),
                    mark_price=float(r["mark_price"] or 0.0),
                    interval_hours=interval,
                )
            )
        except (TypeError, ValueError):
            continue
    return out


def _group_by_ts(snaps: list[_Snap]) -> list[tuple[datetime, list[_Snap]]]:
    """Сгруппировать снимки по точному ts (один скан-тик бота)."""
    if not snaps:
        return []
    out: list[tuple[datetime, list[_Snap]]] = []
    cur_ts = snaps[0].ts
    cur_bucket: list[_Snap] = []
    for s in snaps:
        if s.ts == cur_ts:
            cur_bucket.append(s)
        else:
            out.append((cur_ts, cur_bucket))
            cur_ts = s.ts
            cur_bucket = [s]
    out.append((cur_ts, cur_bucket))
    return out


# --- Финансовые помощники --------------------------------------------

def _fee_rate(exchange: str) -> float:
    """Taker-fee с учётом конфига (как в arbitrage_engine._taker_fee_for)."""
    fees = getattr(config, "FUNDING_TAKER_FEES", {}) or {}
    return float(fees.get(exchange.lower(), fees.get("default", 0.0006)))


def _estimate_pair_fees(notional_usdt: float, long_ex: str, short_ex: str) -> float:
    """Round-trip taker-fee: 4 takera (open+close на обеих биржах).

    Полностью совпадает с arb_executor._estimate_fees, но дублируем
    локально, чтобы не тащить тяжёлый импорт executor'а в CLI.
    """
    return notional_usdt * (2.0 * _fee_rate(long_ex) + 2.0 * _fee_rate(short_ex))


def _fee_drag_apr(taker_fee: float, holding_days: float) -> float:
    """Стоимость 2× takera, разнесённая на holding_days и приведённая к APR.

    Совпадает с arbitrage_engine._fee_drag_apr — нужна для консистентного
    расчёта net_edge_apr (порог входа сравнивается именно с ним).
    """
    if holding_days <= 0:
        return 0.0
    return (2.0 * taker_fee) * (365.0 / holding_days)


# --- Предрасчёт пар на каждый ts -------------------------------------

@dataclass
class _PairCandidate:
    """Готовый кандидат для входа на конкретном ts."""

    symbol: str
    long_ex: str
    short_ex: str
    long_rate: float
    short_rate: float
    long_interval: float
    short_interval: float
    edge_per_hour: float
    net_edge_apr: float


def _build_tick(
    snaps_at_ts: list[_Snap],
    holding_days: float,
) -> tuple[dict[tuple[str, str], _Snap], list[_PairCandidate]]:
    """По срезу одного ts вернуть:
    - lookup (symbol, exchange) -> _Snap (для мониторинга открытых пар);
    - список всех cross-exchange пар, отсортированных по net_edge_apr desc.

    Кандидаты строятся как в arbitrage_engine.cross_exchange_pairs:
    LONG = нога с меньшим funding_rate, SHORT = с большим. edge_per_hour
    в пересчёте на час, чтобы корректно учесть разные интервалы (8/4/1ч)
    между биржами.
    """
    by_symbol: dict[str, list[_Snap]] = {}
    lookup: dict[tuple[str, str], _Snap] = {}
    for s in snaps_at_ts:
        by_symbol.setdefault(s.symbol, []).append(s)
        lookup[(s.symbol, s.exchange)] = s

    candidates: list[_PairCandidate] = []
    for symbol, group in by_symbol.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                long_leg, short_leg = (a, b) if a.rate <= b.rate else (b, a)
                long_per_h = long_leg.rate / max(long_leg.interval_hours, 1e-9)
                short_per_h = short_leg.rate / max(short_leg.interval_hours, 1e-9)
                edge_per_h = short_per_h - long_per_h
                edge_apr = edge_per_h * 24.0 * 365.0
                fee_drag = (
                    _fee_drag_apr(_fee_rate(long_leg.exchange), holding_days)
                    + _fee_drag_apr(_fee_rate(short_leg.exchange), holding_days)
                )
                candidates.append(
                    _PairCandidate(
                        symbol=symbol,
                        long_ex=long_leg.exchange,
                        short_ex=short_leg.exchange,
                        long_rate=long_leg.rate,
                        short_rate=short_leg.rate,
                        long_interval=long_leg.interval_hours,
                        short_interval=short_leg.interval_hours,
                        edge_per_hour=edge_per_h,
                        net_edge_apr=edge_apr - fee_drag,
                    )
                )
    candidates.sort(key=lambda c: c.net_edge_apr, reverse=True)
    return lookup, candidates


# --- Симуляция -------------------------------------------------------

@dataclass
class _OpenPos:
    """Активная позиция в симуляции."""

    symbol: str
    long_ex: str
    short_ex: str
    open_ts: datetime
    last_update: datetime
    funding_received: float
    open_net_apr: float


def _edge_per_hour(long_snap: _Snap, short_snap: _Snap) -> float:
    """Чистый edge (доход на 1 час) для конкретной пары ног."""
    long_per_h = long_snap.rate / max(long_snap.interval_hours, 1e-9)
    short_per_h = short_snap.rate / max(short_snap.interval_hours, 1e-9)
    return short_per_h - long_per_h


def _simulate(
    ticks: list[tuple[datetime, dict[tuple[str, str], _Snap], list[_PairCandidate]]],
    open_thr: float,
    close_thr: float,
    max_hold_h: float,
    notional: float,
) -> list[_Trade]:
    """Прогнать историю по тикам с заданными параметрами.

    Возвращает список завершённых сделок. Активные на момент конца
    истории закрываются принудительно по последнему ts.

    Алгоритм:
      Для каждого ts:
        1) Обновляем все открытые позиции: накапливаем funding_received
           по интегралу edge_per_hour * notional * delta_h. Проверяем
           условия закрытия (current_net_apr <= close_thr ИЛИ
           held_h >= max_hold_h).
        2) Проходим по отсортированным кандидатам и открываем те,
           у которых net_edge_apr >= open_thr и нет активной позиции
           по этому символу.

    Симуляция полностью детерминированная.
    """
    active: dict[str, _OpenPos] = {}
    closed: list[_Trade] = []
    if not ticks:
        return closed

    # holding_days в _build_tick зашит в net_edge_apr. Для ПОВТОРНОГО
    # вычисления текущего edge активной пары использовать ту же формулу
    # необязательно — мы просто считаем edge_apr БЕЗ fee_drag и сравниваем
    # с close_thr. close_thr трактуется как "edge упал ниже X% APR" —
    # это то, что хочет пользователь. Fee drag amortизирован уже в open
    # моменте; в close его учитывать заново — двойной счёт.
    for ts_now, lookup, candidates in ticks:
        # 1) Обновляем активные.
        for symbol in list(active):
            pos = active[symbol]
            long_snap = lookup.get((symbol, pos.long_ex))
            short_snap = lookup.get((symbol, pos.short_ex))
            held_h = (ts_now - pos.open_ts).total_seconds() / 3600.0

            # Если на этом ts хотя бы одной ноги нет — данные пропали
            # (например, биржа в OPEN circuit breaker). Накопление
            # пропускаем, но time-stop всё равно работает.
            if long_snap and short_snap:
                edge_per_h = _edge_per_hour(long_snap, short_snap)
                delta_h = (ts_now - pos.last_update).total_seconds() / 3600.0
                if delta_h > 0:
                    pos.funding_received += edge_per_h * notional * delta_h
                pos.last_update = ts_now
                current_apr = edge_per_h * 24.0 * 365.0
                edge_below = current_apr <= close_thr
            else:
                # Без свежих данных не закрываем по edge, только по time-stop.
                edge_below = False

            time_stop = held_h >= max_hold_h
            if edge_below or time_stop:
                fees = _estimate_pair_fees(notional, pos.long_ex, pos.short_ex)
                closed.append(
                    _Trade(
                        symbol=symbol,
                        long_ex=pos.long_ex,
                        short_ex=pos.short_ex,
                        open_ts=pos.open_ts,
                        close_ts=ts_now,
                        held_hours=held_h,
                        funding_received=pos.funding_received,
                        fees=fees,
                        pnl=pos.funding_received - fees,
                    )
                )
                del active[symbol]

        # 2) Открываем новые. Кандидаты уже отсортированы по net_edge_apr.
        for cand in candidates:
            if cand.net_edge_apr < open_thr:
                # Список отсортирован по убыванию — дальше только хуже.
                break
            if cand.symbol in active:
                continue
            active[cand.symbol] = _OpenPos(
                symbol=cand.symbol,
                long_ex=cand.long_ex,
                short_ex=cand.short_ex,
                open_ts=ts_now,
                last_update=ts_now,
                funding_received=0.0,
                open_net_apr=cand.net_edge_apr,
            )

    # Принудительное закрытие хвостов на последнем ts.
    last_ts = ticks[-1][0]
    for symbol, pos in list(active.items()):
        held_h = (last_ts - pos.open_ts).total_seconds() / 3600.0
        fees = _estimate_pair_fees(notional, pos.long_ex, pos.short_ex)
        closed.append(
            _Trade(
                symbol=symbol,
                long_ex=pos.long_ex,
                short_ex=pos.short_ex,
                open_ts=pos.open_ts,
                close_ts=last_ts,
                held_hours=held_h,
                funding_received=pos.funding_received,
                fees=fees,
                pnl=pos.funding_received - fees,
            )
        )

    return closed


# --- Метрики ---------------------------------------------------------

def _compute_metrics(
    open_thr: float,
    close_thr: float,
    max_hold_h: float,
    trades: list[_Trade],
) -> _ComboResult:
    """Посчитать сводные метрики по списку сделок."""
    n = len(trades)
    if n == 0:
        return _ComboResult(
            open_thr=open_thr,
            close_thr=close_thr,
            max_hold_h=max_hold_h,
            n_trades=0,
            total_pnl=0.0,
            mean_pnl=0.0,
            win_rate=0.0,
            sharpe_proxy=0.0,
            max_drawdown=0.0,
        )

    pnls = [t.pnl for t in trades]
    total_pnl = sum(pnls)
    mean_pnl = total_pnl / n
    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / n

    # Sharpe-proxy = mean / stdev. Для одной сделки stdev неопределён → 0.
    if n > 1:
        try:
            stdev = statistics.stdev(pnls)
        except statistics.StatisticsError:
            stdev = 0.0
        if stdev > 1e-9:
            sharpe = mean_pnl / stdev
        elif mean_pnl > 0:
            # Все сделки одинаково прибыльные — даём очень высокий скор,
            # но конечный (чтобы не получить inf при сортировке).
            sharpe = 10.0
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # Max drawdown на cumulative pnl.
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    return _ComboResult(
        open_thr=open_thr,
        close_thr=close_thr,
        max_hold_h=max_hold_h,
        n_trades=n,
        total_pnl=total_pnl,
        mean_pnl=mean_pnl,
        win_rate=win_rate,
        sharpe_proxy=sharpe,
        max_drawdown=max_dd,
    )


# --- Главный цикл ----------------------------------------------------

def optimize(
    snaps: list[_Snap],
    notional: float,
    min_trades: int,
    top: int,
) -> list[_ComboResult]:
    """Прогнать всю grid и вернуть топ-N комбо.

    Симуляция выполняется по полностью предрасчитанным тикам
    (lookup + кандидаты), что позволяет ускорить grid-search в N раз.
    """
    if not snaps:
        return []

    grouped = _group_by_ts(snaps)

    # Предрасчёт тиков. holding_days берём из конфига (для consistency
    # с production net_edge_apr; пользователь сравнивает open_threshold
    # именно с этой величиной). Используем default из config, не из grid:
    # max_hold_hours варьируется, а fee_drag должен быть фиксированной
    # constant'ой, чтобы пороги в grid интерпретировались одинаково.
    holding_days = float(getattr(config, "FUNDING_HOLDING_DAYS", 7.0))
    ticks: list[tuple[datetime, dict[tuple[str, str], _Snap], list[_PairCandidate]]] = []
    for ts, bucket in grouped:
        lookup, cands = _build_tick(bucket, holding_days)
        ticks.append((ts, lookup, cands))

    results: list[_ComboResult] = []
    for open_thr in OPEN_THRESHOLDS:
        for close_thr in CLOSE_THRESHOLDS:
            if close_thr >= open_thr:
                # Нонсенс-комбинация: порог выхода >= порогу входа,
                # позиция закроется сразу после открытия.
                continue
            for max_hold_h in MAX_HOLD_HOURS_GRID:
                trades = _simulate(
                    ticks, open_thr, close_thr, max_hold_h, notional
                )
                metrics = _compute_metrics(open_thr, close_thr, max_hold_h, trades)
                results.append(metrics)

    # Фильтр по min_trades, сортировка по sharpe_proxy.
    qualified = [r for r in results if r.n_trades >= min_trades]
    qualified.sort(key=lambda r: r.sharpe_proxy, reverse=True)
    return qualified[: max(1, top)]


# --- Вывод и сохранение ---------------------------------------------

def _format_table(results: list[_ComboResult]) -> str:
    """Моноширинная таблица топ-комбо."""
    header = (
        f"{'open_thr':>9} {'close_thr':>10} {'max_hold_h':>11} "
        f"{'n_trades':>9} {'total_pnl':>11} {'mean_pnl':>10} "
        f"{'win_rate':>9} {'sharpe':>8} {'max_dd':>10}"
    )
    lines = [header, "-" * len(header)]
    for r in results:
        lines.append(
            f"{r.open_thr*100:>8.1f}% {r.close_thr*100:>9.1f}% "
            f"{r.max_hold_h:>11.0f} {r.n_trades:>9d} "
            f"{r.total_pnl:>+11.2f} {r.mean_pnl:>+10.3f} "
            f"{r.win_rate*100:>8.1f}% {r.sharpe_proxy:>8.3f} "
            f"{r.max_drawdown:>10.2f}"
        )
    return "\n".join(lines)


def _save_best(path: str, best: _ComboResult) -> None:
    """Записать рекомендуемые значения в .env-формате."""
    lines = [
        "# Сгенерировано optimize.py — рекомендованные пороги",
        f"# (на основе walk-forward анализа истории funding_snapshots)",
        f"# n_trades={best.n_trades}, total_pnl={best.total_pnl:+.2f} USDT, "
        f"sharpe={best.sharpe_proxy:.3f}",
        f"ARB_OPEN_MIN_NET_APR={best.open_thr:.4f}",
        f"ARB_CLOSE_NET_APR={best.close_thr:.4f}",
        f"ARB_MAX_HOLD_HOURS={best.max_hold_h:.0f}",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --- CLI -------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="optimize.py",
        description=(
            "Подбор оптимальных порогов funding-арбитража по истории "
            "funding_snapshots в SQLite."
        ),
    )
    p.add_argument(
        "--days",
        type=int,
        default=30,
        help="Сколько дней истории брать (default 30).",
    )
    p.add_argument(
        "--min-trades",
        type=int,
        default=10,
        help="Минимум сделок, чтобы комбо засчитывалось (default 10).",
    )
    p.add_argument(
        "--save-best",
        type=str,
        default=None,
        help="Записать лучший комбо в .env-файл по этому пути.",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        help="Сколько строк показать в таблице (default 10).",
    )
    p.add_argument(
        "--db",
        type=str,
        default=None,
        help="Путь к SQLite (по умолчанию memory.DB_PATH).",
    )
    p.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Фильтр по символам, через запятую: BTCUSDT,ETHUSDT.",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    db_path = args.db or memory.DB_PATH
    symbols_filter: Optional[set[str]] = None
    if args.symbols:
        symbols_filter = {
            s.strip().upper() for s in args.symbols.split(",") if s.strip()
        }

    snaps = _load_snapshots(db_path, args.days, symbols_filter)
    if len(snaps) < 100:
        print(
            "[OPTIMIZE] Недостаточно данных для оптимизации "
            "(нужно собрать историю за неделю работы бота)"
        )
        return 0

    notional = float(getattr(config, "ARB_NOTIONAL_USDT", 200.0))

    print(
        f"[OPTIMIZE] Загружено {len(snaps)} снимков за {args.days} дней. "
        f"Notional={notional:.0f} USDT. Запускаю grid-search..."
    )

    best_list = optimize(snaps, notional, args.min_trades, args.top)
    if not best_list:
        print(
            f"[OPTIMIZE] Нет ни одного комбо с n_trades >= {args.min_trades}. "
            f"Попробуйте уменьшить --min-trades или собрать больше истории."
        )
        return 0

    print()
    print(f"Топ-{len(best_list)} по sharpe_proxy (min_trades={args.min_trades}):")
    print(_format_table(best_list))
    print()
    print(
        f"Лучший: open={best_list[0].open_thr*100:.1f}% "
        f"close={best_list[0].close_thr*100:.1f}% "
        f"max_hold_h={best_list[0].max_hold_h:.0f}, "
        f"PnL={best_list[0].total_pnl:+.2f} USDT, "
        f"sharpe={best_list[0].sharpe_proxy:.3f}"
    )

    if args.save_best:
        _save_best(args.save_best, best_list[0])
        print(f"[OPTIMIZE] Лучший комбо записан в {args.save_best}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
