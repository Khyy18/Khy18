"""Funding rate / cross-exchange arbitrage scanner (read-only).

ФАЗА 1 плана автоматизированного арбитража: модуль НЕ торгует, он только
снимает срез funding по N биржам и считает оценку доходности (APR с учётом
taker-комиссий за вход и выход хеджа).

Поддерживаемые сценарии:
  1) Cash-and-carry на одной бирже:
       - LONG спот / SHORT перп при funding > 0 (платят шорту);
       - SHORT спот (или ничего) / LONG перп при funding < 0 (платят лонгу).
     Здесь оцениваем именно "перп-нога": сколько годовых платит/получает
     по текущему funding. Это потолок доходности carry-структуры,
     потому что спот-ноге funding не платится.
  2) Кросс-биржевой carry: LONG perp на бирже A + SHORT perp на бирже B
     по тому же символу, если funding на A значительно отрицательнее B
     (или наоборот). PnL = funding_B - funding_A за каждый интервал.

ВАЖНО ПРО ИНТЕРВАЛЫ. Биржи рассчитывают funding раз в 8/4/1 час - это
закладывается в interval_hours внутри dict из adapter.get_funding_info.
APR считается как:
    APR = funding_rate * (24 / interval_hours) * 365

Комиссии. На funding-арбитраже хедж надо открыть и закрыть. Для оценки
порога рентабельности учитываем 2 * taker_fee (вход + выход) - это будет
"стоимость удержания позиции один раз". Чтобы сравнивать в одной шкале с
APR, делим эту стоимость на гипотетическое время удержания
FUNDING_HOLDING_DAYS (по умолчанию 7 дней) и пересчитываем в APR.

    fee_drag_apr = (2 * taker_fee) * (365 / holding_days)

Итоговый "net APR" = APR - fee_drag_apr. Это очень грубая оценка - мы
игнорируем slippage, изменение funding со временем и риск ликвидации.
Но она достаточна, чтобы НЕ показывать пользователю инструмент с
funding 0.005% за 8ч (= 5.5% APR) как "интересный": на typical taker
0.05% × 2 = 0.1% и удержании неделю это уже отрицательная карри.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import config


# Узкий неразрывный пробел и истинный минус - чтобы числа в Telegram
# смотрелись консистентно (см. learning про моноширинные карточки).
_NBSP = "\u202f"
_MINUS = "\u2212"


# --- Структуры данных ----------------------------------------------------

@dataclass
class FundingSnapshot:
    """Один срез funding по (биржа, символ).

    apr - "брутто" APR без учёта комиссий (только funding-доход).
    net_apr - после вычета fee_drag_apr (см. модульный docstring).
    side_recommendation - "SHORT_PERP" если funding > 0 (получаем funding),
    "LONG_PERP" если funding < 0, "FLAT" если близко к нулю.
    """
    exchange: str
    symbol: str
    funding_rate: float
    next_funding_ts: int
    mark_price: float
    interval_hours: float
    apr: float = 0.0
    net_apr: float = 0.0
    side_recommendation: str = "FLAT"
    fetched_epoch: float = field(default_factory=time.time)


@dataclass
class CrossPair:
    """Кросс-биржевая carry-пара по одному символу.

    long_leg - адрес биржи, где идём в LONG perp (там funding ниже / отрицательнее).
    short_leg - адрес биржи, где идём в SHORT perp.
    edge_per_interval - сумма funding получаемого SHORT-ногой минус
        funding платимого LONG-ногой за один общий "тик" (приведено к
        одному часу: rate * 1/interval_hours, потом домножено на 24*365).
    """
    symbol: str
    long_leg: FundingSnapshot
    short_leg: FundingSnapshot
    edge_apr: float
    net_edge_apr: float


# --- Внутренние помощники ------------------------------------------------

def _classify_side(funding_rate: float, threshold: float = 1e-5) -> str:
    if funding_rate > threshold:
        return "SHORT_PERP"
    if funding_rate < -threshold:
        return "LONG_PERP"
    return "FLAT"


def _to_apr(funding_rate: float, interval_hours: float) -> float:
    """Funding rate за один интервал -> годовая доходность."""
    if interval_hours <= 0:
        return 0.0
    intervals_per_day = 24.0 / interval_hours
    return funding_rate * intervals_per_day * 365.0


def _fee_drag_apr(taker_fee: float, holding_days: float) -> float:
    """Эквивалент 2*taker_fee, разнесённый на holding_days и приведённый к APR."""
    if holding_days <= 0:
        return 0.0
    return (2.0 * taker_fee) * (365.0 / holding_days)


def _taker_fee_for(exchange: str) -> float:
    fees = getattr(config, "FUNDING_TAKER_FEES", {}) or {}
    # 0.0006 = 0.06% - дефолт по taker для большинства бирж.
    return float(fees.get(exchange.lower(), fees.get("default", 0.0006)))


# --- Публичные форматтеры ------------------------------------------------

def format_pct(value: float, decimals: int = 4) -> str:
    """0.0001 -> '0.0100%' (с истинным минусом для отрицательных)."""
    sign = _MINUS if value < 0 else ""
    return f"{sign}{abs(value) * 100:.{decimals}f}%"


def format_apr(value: float, decimals: int = 2) -> str:
    sign = _MINUS if value < 0 else ""
    return f"{sign}{abs(value) * 100:.{decimals}f}%"


# --- Сканер --------------------------------------------------------------

async def _scan_one(
    session: Any,
    adapter: Any,
    exchange_name: str,
    symbols: list[str],
    holding_days: float,
) -> list[FundingSnapshot]:
    """Снять funding по всем symbols одной биржи."""
    taker = _taker_fee_for(exchange_name)
    fee_drag = _fee_drag_apr(taker, holding_days)

    async def _one(sym: str) -> Optional[FundingSnapshot]:
        try:
            info = await adapter.get_funding_info(session, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB] {exchange_name}/{sym}: ошибка get_funding_info: {exc}")
            return None
        if not info:
            return None
        try:
            rate = float(info["funding_rate"])
            interval_h = float(info["interval_hours"])
            mark = float(info["mark_price"])
            next_ts = int(info["next_funding_ts"])
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[ARB] {exchange_name}/{sym}: некорректный формат: {exc}")
            return None
        apr = _to_apr(rate, interval_h)
        snap = FundingSnapshot(
            exchange=exchange_name,
            symbol=sym,
            funding_rate=rate,
            next_funding_ts=next_ts,
            mark_price=mark,
            interval_hours=interval_h,
            apr=apr,
            net_apr=apr - fee_drag if apr > 0 else apr + fee_drag,
            side_recommendation=_classify_side(rate),
        )
        return snap

    tasks = [_one(s) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r is not None]


async def scan_funding(
    session: Any,
    adapters: dict[str, Any],
    symbols: Optional[list[str]] = None,
    holding_days: Optional[float] = None,
) -> dict[str, list[FundingSnapshot]]:
    """Полный скан funding по нескольким биржам.

    Возвращает {exchange_name: [FundingSnapshot, ...]}.
    Биржи опрашиваются параллельно; внутри каждой биржи символы тоже
    параллельно. Если адаптер биржи не реализует get_funding_info -
    результат пустой список (тихо).
    """
    if symbols is None:
        symbols = list(getattr(config, "FUNDING_SCAN_SYMBOLS", ()))
    if holding_days is None:
        holding_days = float(getattr(config, "FUNDING_HOLDING_DAYS", 7.0))

    async def _per_exchange(name: str, adapter: Any) -> tuple[str, list[FundingSnapshot]]:
        snaps = await _scan_one(session, adapter, name, symbols, holding_days)
        return name, snaps

    results = await asyncio.gather(
        *[_per_exchange(n, a) for n, a in adapters.items()],
        return_exceptions=False,
    )
    return {name: snaps for name, snaps in results}


def top_by_apr(
    snapshots: dict[str, list[FundingSnapshot]],
    limit: int = 10,
    min_abs_apr: float = 0.0,
) -> list[FundingSnapshot]:
    """Все срезы из всех бирж - в один список, сортировка по |net_apr|.

    min_abs_apr фильтрует мусор: если |net_apr| меньше этого порога
    (например 5%), такие записи не попадают в топ. Это нужно, чтобы
    NIL-funding инструменты не разбавляли список.
    """
    flat: list[FundingSnapshot] = []
    for snaps in snapshots.values():
        flat.extend(snaps)
    flat = [s for s in flat if abs(s.net_apr) >= min_abs_apr]
    flat.sort(key=lambda s: abs(s.net_apr), reverse=True)
    return flat[:limit]


def cross_exchange_pairs(
    snapshots: dict[str, list[FundingSnapshot]],
    holding_days: Optional[float] = None,
    min_edge_apr: float = 0.0,
) -> list[CrossPair]:
    """Найти carry-пары: один и тот же символ на двух биржах с разным funding.

    Идея: если на бирже A funding = -0.02% за 8ч, а на бирже B = +0.01%
    за 8ч, то LONG perp на A (платят нам) + SHORT perp на B (платят нам)
    = карри 0.03% за 8ч ≈ 33% APR без направленной экспозиции.

    Прибыль на пару intervals: (funding_B - funding_A) при допущении что
    оба интервала равны. Если intervals разные (один 8ч, другой 4ч) -
    приводим оба к "доход за 1 час" перед суммированием.
    """
    if holding_days is None:
        holding_days = float(getattr(config, "FUNDING_HOLDING_DAYS", 7.0))

    # Перегруппировать по символу.
    by_symbol: dict[str, list[FundingSnapshot]] = {}
    for snaps in snapshots.values():
        for s in snaps:
            by_symbol.setdefault(s.symbol, []).append(s)

    out: list[CrossPair] = []
    for symbol, group in by_symbol.items():
        if len(group) < 2:
            continue
        # Перебираем все пары на этом символе.
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                # Сторона LONG - там, где funding меньше (платим меньше или нам платят).
                long_leg, short_leg = (a, b) if a.funding_rate <= b.funding_rate else (b, a)

                # Доход на 1 час: (rate / interval_h) для каждой ноги.
                long_per_hour = long_leg.funding_rate / max(long_leg.interval_hours, 1e-9)
                short_per_hour = short_leg.funding_rate / max(short_leg.interval_hours, 1e-9)
                # SHORT нога получает funding (если положительный), LONG нога платит.
                # Чистая carry за час = short_per_hour - long_per_hour.
                edge_per_hour = short_per_hour - long_per_hour
                edge_apr = edge_per_hour * 24.0 * 365.0

                # Комиссии: открыть + закрыть на ОБЕИХ биржах = 4 takers.
                fee_drag = (
                    _fee_drag_apr(_taker_fee_for(long_leg.exchange), holding_days)
                    + _fee_drag_apr(_taker_fee_for(short_leg.exchange), holding_days)
                )
                net_edge_apr = edge_apr - fee_drag

                if net_edge_apr < min_edge_apr:
                    continue

                out.append(
                    CrossPair(
                        symbol=symbol,
                        long_leg=long_leg,
                        short_leg=short_leg,
                        edge_apr=edge_apr,
                        net_edge_apr=net_edge_apr,
                    )
                )
    out.sort(key=lambda p: p.net_edge_apr, reverse=True)
    return out


# --- Telegram-форматтеры -------------------------------------------------

_DIVIDER = "\u2501" * 24  # ━ × 24


def _format_money(value: float) -> str:
    """1234567.89 -> '1 234 568' с U+202F."""
    int_part = int(round(value))
    s = f"{int_part:,}".replace(",", _NBSP)
    return s


def format_top_funding(
    top: list[FundingSnapshot],
    title: str = "TOP FUNDING (одна биржа)",
) -> str:
    """Моноширинная карточка с топом срезов по |net_apr|."""
    if not top:
        return (
            "<pre>"
            f"📡 {title}\n"
            f"{_DIVIDER}\n"
            "Срезов выше порога нет.\n"
            "</pre>"
        )

    lines = [f"📡 {title}", _DIVIDER]
    # Заголовок таблицы: BIRGA  SYM        FUND%   APR%   NET%   SIDE
    lines.append("биржа    символ     funding   APR     net APR   сторона")
    for s in top:
        sym = (s.symbol or "")[:10].ljust(10)
        ex = (s.exchange or "")[:7].ljust(7)
        fund_str = format_pct(s.funding_rate).rjust(8)
        apr_str = format_apr(s.apr).rjust(7)
        net_str = format_apr(s.net_apr).rjust(8)
        side_short = {
            "SHORT_PERP": "SHORT↘",
            "LONG_PERP": "LONG↗",
            "FLAT": "FLAT  ",
        }.get(s.side_recommendation, "?")
        lines.append(f"{ex}  {sym} {fund_str}  {apr_str}  {net_str}  {side_short}")

    lines.append(_DIVIDER)
    lines.append(
        f"holding={int(getattr(config, 'FUNDING_HOLDING_DAYS', 7))}д, "
        f"taker fee учтён ×2 за цикл"
    )
    return "<pre>" + "\n".join(lines) + "</pre>"


def format_cross_pairs(
    pairs: list[CrossPair],
    title: str = "CROSS-EXCHANGE CARRY",
    limit: int = 10,
) -> str:
    """Моноширинная карточка с топом кросс-биржевых пар."""
    pairs = pairs[:limit]
    if not pairs:
        return (
            "<pre>"
            f"🔀 {title}\n"
            f"{_DIVIDER}\n"
            "Пар выше порога нет.\n"
            "</pre>"
        )

    lines = [f"🔀 {title}", _DIVIDER]
    lines.append("символ      LONG@         SHORT@        edge APR  net APR")
    for p in pairs:
        sym = (p.symbol or "")[:10].ljust(10)
        long_at = f"{p.long_leg.exchange}({format_pct(p.long_leg.funding_rate, 3)})"[:13].ljust(13)
        short_at = f"{p.short_leg.exchange}({format_pct(p.short_leg.funding_rate, 3)})"[:13].ljust(13)
        edge = format_apr(p.edge_apr).rjust(8)
        net = format_apr(p.net_edge_apr).rjust(8)
        lines.append(f"{sym} {long_at} {short_at} {edge}  {net}")

    lines.append(_DIVIDER)
    lines.append(
        "LONG perp на левой ноге + SHORT perp на правой; "
        "обе комиссии (2×open+2×close) учтены."
    )
    return "<pre>" + "\n".join(lines) + "</pre>"


def format_full_report(
    snapshots: dict[str, list[FundingSnapshot]],
    top_limit: int = 10,
    cross_limit: int = 5,
) -> str:
    """Сводный отчёт: top funding + cross pairs."""
    min_abs_apr = float(getattr(config, "FUNDING_TOP_MIN_ABS_APR", 0.05))  # 5% APR
    min_edge_apr = float(getattr(config, "FUNDING_CROSS_MIN_EDGE_APR", 0.10))  # 10% APR

    top = top_by_apr(snapshots, limit=top_limit, min_abs_apr=min_abs_apr)
    pairs = cross_exchange_pairs(snapshots, min_edge_apr=min_edge_apr)

    parts: list[str] = []
    parts.append(format_top_funding(top))
    parts.append("")
    parts.append(format_cross_pairs(pairs, limit=cross_limit))
    return "\n".join(parts)
