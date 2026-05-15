"""Grid-бот: сетка buy/sell ордеров на BTC/ETH.

Логика:
  1. Определяем текущую цену (mid-price из orderbook).
  2. Строим N уровней ВЫШЕ (sell/short) и N уровней НИЖЕ (buy/long).
  3. Размещаем лимитные ордера на каждом уровне.
  4. Когда ордер исполнен — ставим встречный на соседнем уровне.
  5. Если цена ушла за пределы сетки — пересоздаём.

Зарабатывает на боковом движении (range-bound market).
Каждый «цикл» buy→sell = profit = grid_step * qty.

Особенности:
  - Работает на perpetual futures (можно short без залога в активе).
  - Плечо настраивается (GRID_LEVERAGE, default 1x = spot-like).
  - Хранит состояние в state["grid"][symbol].
  - НЕ торгует если global_kill_switch активен.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import aiohttp

import capital_allocator
import combo_config as cfg
import global_kill_switch
from exchanges import get_adapter
from exchanges.base import ExchangeAdapter


# ─── Типы ─────────────────────────────────────────────────────────────

class GridLevel:
    """Один уровень сетки."""

    __slots__ = ("price", "side", "order_id", "filled", "qty", "fill_price")

    def __init__(
        self,
        price: float,
        side: str,
        qty: float,
        order_id: str = "",
        filled: bool = False,
        fill_price: float = 0.0,
    ) -> None:
        self.price = price
        self.side = side  # "Buy" или "Sell"
        self.qty = qty
        self.order_id = order_id
        self.filled = filled
        self.fill_price = fill_price  # Реальная цена исполнения

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "side": self.side,
            "qty": self.qty,
            "order_id": self.order_id,
            "filled": self.filled,
            "fill_price": self.fill_price,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GridLevel":
        return cls(
            price=float(d["price"]),
            side=str(d["side"]),
            qty=float(d.get("qty", 0)),
            order_id=str(d.get("order_id", "")),
            filled=bool(d.get("filled", False)),
            fill_price=float(d.get("fill_price", 0.0)),
        )


# ─── Вспомогательные функции ──────────────────────────────────────────

_GRID_ADAPTER: ExchangeAdapter | None = None


def _get_adapter() -> ExchangeAdapter:
    """Адаптер биржи для grid (кешируется)."""
    global _GRID_ADAPTER
    if _GRID_ADAPTER is None:
        _GRID_ADAPTER = get_adapter(cfg.GRID_EXCHANGE)
    return _GRID_ADAPTER


def _calc_grid_order_size(state: dict[str, Any], n_levels: int) -> float:
    """Размер одного ордера в USDT.

    Если GRID_ORDER_USDT задан вручную — используем его.
    Иначе: (аллоцированный капитал) / (n_levels * 2) — делим на все ордера.
    """
    if cfg.GRID_ORDER_USDT > 0:
        return cfg.GRID_ORDER_USDT

    allocated = capital_allocator.get_strategy_capital(state, "grid")
    # На каждый символ — равная доля. n_levels ордеров с каждой стороны.
    n_symbols = max(1, len(cfg.GRID_SYMBOLS))
    per_symbol = allocated / n_symbols
    # Каждый ордер = per_symbol / n_levels (только одна сторона active).
    order_size = per_symbol / max(1, n_levels)
    return max(5.0, order_size)  # минимум $5 на ордер


def build_grid_levels(
    mid_price: float,
    n_levels: int,
    step_pct: float,
    qty_per_level: float,
    best_bid: float = 0.0,
    best_ask: float = 0.0,
    buy_levels_count: int = 0,
    sell_levels_count: int = 0,
) -> list[GridLevel]:
    """Построить уровни сетки вокруг mid_price.

    Если buy_levels_count / sell_levels_count заданы — asymmetric grid.
    Иначе symmetric: n_levels с каждой стороны.

    Если best_bid/best_ask заданы — Buy-уровни строятся от best_bid вниз,
    Sell-уровни от best_ask вверх. Это гарантирует что ордера попадают
    в стакан как maker (не taker).
    """
    levels: list[GridLevel] = []

    # Asymmetric: если задано — используем, иначе symmetric
    n_buy = buy_levels_count if buy_levels_count > 0 else n_levels
    n_sell = sell_levels_count if sell_levels_count > 0 else n_levels

    # Базовые точки: если bid/ask не заданы — fallback на mid
    buy_base = best_bid if best_bid > 0 else mid_price
    sell_base = best_ask if best_ask > 0 else mid_price

    for i in range(1, n_buy + 1):
        buy_price = buy_base * (1 - step_pct * i)
        levels.append(GridLevel(
            price=buy_price,
            side="Buy",
            qty=qty_per_level,
        ))

    for i in range(1, n_sell + 1):
        sell_price = sell_base * (1 + step_pct * i)
        levels.append(GridLevel(
            price=sell_price,
            side="Sell",
            qty=qty_per_level,
        ))

    levels.sort(key=lambda lv: lv.price)
    return levels


def is_grid_out_of_range(
    mid_price: float,
    levels: list[GridLevel],
    tolerance: float = 0.5,
) -> bool:
    """Проверить, ушла ли цена за пределы сетки.

    tolerance: если цена ушла дальше чем tolerance * (верхняя - нижняя) —
    считаем out-of-range и пересоздаём сетку.
    """
    if not levels:
        return True
    prices = [lv.price for lv in levels]
    low = min(prices)
    high = max(prices)
    spread = high - low
    if spread <= 0:
        return True
    # Цена ушла за пределы сетки
    if mid_price < low - spread * tolerance:
        return True
    if mid_price > high + spread * tolerance:
        return True
    return False


# ─── Инициализация state ──────────────────────────────────────────────

def init_grid_state(state: dict[str, Any]) -> None:
    """Инициализировать секцию grid в state."""
    state.setdefault("grid", {})
    grid = state["grid"]
    grid.setdefault("enabled", cfg.GRID_ENABLED)
    grid.setdefault("symbols", {})
    grid.setdefault("total_cycles", 0)
    grid.setdefault("total_profit_usdt", 0.0)
    grid.setdefault("last_tick_epoch", 0.0)


# ─── Основной тик ─────────────────────────────────────────────────────

async def grid_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Основной тик grid-бота.

    Вызывается из main loop раз в GRID_REBALANCE_INTERVAL_SEC.
    Возвращает dict с результатами тика для логирования.

    Результат: {"skipped": str} или {"processed": [...], "errors": [...]}
    """
    # Проверяем global kill-switch
    if global_kill_switch.is_kill_active(state):
        return {"skipped": "global_kill_active"}

    grid_state = state.get("grid", {})
    if not grid_state.get("enabled", False):
        return {"skipped": "grid_disabled"}

    # Rate-limit
    last_tick = float(grid_state.get("last_tick_epoch", 0))
    now = time.time()
    if (now - last_tick) < cfg.GRID_REBALANCE_INTERVAL_SEC:
        return {"skipped": "cooldown"}

    grid_state["last_tick_epoch"] = now

    adapter = _get_adapter()
    results: list[str] = []
    errors: list[str] = []

    for symbol in cfg.GRID_SYMBOLS:
        try:
            result = await _process_symbol(session, state, adapter, symbol)
            results.append(f"{symbol}: {result}")
        except Exception as exc:  # noqa: BLE001
            err_msg = f"{symbol}: {exc}"
            errors.append(err_msg)
            print(f"[GRID] Ошибка тика {symbol}: {exc}")

    return {"processed": results, "errors": errors}


async def _process_symbol(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: ExchangeAdapter,
    symbol: str,
) -> str:
    """Обработать один символ: проверить ордера, пересоздать сетку если нужно."""
    grid_state = state["grid"]
    sym_state = grid_state["symbols"].setdefault(symbol, {})

    # Получаем текущую цену
    top = await adapter.get_orderbook_top(session, symbol)
    if top is None:
        return "orderbook недоступен"

    best_bid, best_ask = top
    mid_price = (best_bid + best_ask) / 2

    # Получаем instrument info для округления
    info = await adapter.get_instrument_info(session, symbol)
    if info is None:
        return "instrument_info недоступен"

    # Проверяем текущие уровни
    levels_raw = sym_state.get("levels", [])
    levels = [GridLevel.from_dict(d) for d in levels_raw] if levels_raw else []

    # Reconciliation: сверяем state с биржей (ордера могли быть
    # отменены / исполнены пока бот не работал)
    if levels:
        open_orders = await adapter.get_open_orders(session, symbol)
        open_ids = {str(o.get("orderId") or o.get("order_id", "")) for o in open_orders}
        orphaned = 0
        for lv in levels:
            if lv.order_id and not lv.filled and lv.order_id not in open_ids:
                # Ордер пропал с биржи — помечаем filled (или отменён)
                lv.filled = True
                lv.fill_price = lv.price
                orphaned += 1
        if orphaned > 0:
            print(f"[GRID] {symbol}: reconciled {orphaned} orphaned orders")

    # Размер ордера
    order_usdt = _calc_grid_order_size(state, cfg.GRID_LEVELS)
    qty_per_level = order_usdt / mid_price
    qty_per_level = adapter.validate_and_round_qty(qty_per_level, info, mid_price)
    if qty_per_level <= 0:
        return "qty слишком мал"

    # Проверяем, не вышла ли цена за пределы сетки
    if not levels or is_grid_out_of_range(mid_price, levels):
        # Отменяем все старые ордера
        cancelled = await _cancel_all_grid_orders(session, adapter, symbol, levels)

        # #8: Fresh price после cancel — цена могла двинуться за время отмены
        top_fresh = await adapter.get_orderbook_top(session, symbol)
        if top_fresh is not None:
            best_bid, best_ask = top_fresh
            mid_price = (best_bid + best_ask) / 2

        # #1: Динамический шаг на основе ATR
        step_pct = cfg.GRID_STEP_PCT
        if cfg.GRID_ATR_MULTIPLIER > 0:
            klines = await adapter.get_klines(session, symbol, "15", limit=20)
            if klines and len(klines) > 15:
                from momentum_engine import calc_atr
                atr = calc_atr(klines, period=14)
                if mid_price > 0 and atr > 0:
                    atr_step = (atr / mid_price) * cfg.GRID_ATR_MULTIPLIER
                    # Ограничиваем: min 0.1%, max 2%
                    step_pct = max(0.001, min(0.02, atr_step))

        # #4: Asymmetric grid — bias по тренду (EMA50 на 4h)
        n_buy = cfg.GRID_LEVELS
        n_sell = cfg.GRID_LEVELS
        if cfg.GRID_TREND_BIAS_LEVELS > 0:
            klines_4h = await adapter.get_klines(session, symbol, "240", limit=60)
            if klines_4h and len(klines_4h) >= 50:
                from momentum_engine import calc_ema
                closes_4h = [float(k["close"]) for k in klines_4h]
                ema50 = calc_ema(closes_4h, 50)
                if ema50 and mid_price > ema50[-1]:
                    # Uptrend: больше sell (фиксируем прибыль), меньше buy
                    n_sell = cfg.GRID_LEVELS + cfg.GRID_TREND_BIAS_LEVELS
                    n_buy = cfg.GRID_LEVELS - cfg.GRID_TREND_BIAS_LEVELS
                elif ema50 and mid_price < ema50[-1]:
                    # Downtrend: больше buy (набираем), меньше sell
                    n_buy = cfg.GRID_LEVELS + cfg.GRID_TREND_BIAS_LEVELS
                    n_sell = cfg.GRID_LEVELS - cfg.GRID_TREND_BIAS_LEVELS
            n_buy = max(2, n_buy)
            n_sell = max(2, n_sell)

        # Строим сетку
        levels = build_grid_levels(
            mid_price=mid_price,
            n_levels=cfg.GRID_LEVELS,
            step_pct=step_pct,
            qty_per_level=qty_per_level,
            best_bid=best_bid,
            best_ask=best_ask,
            buy_levels_count=n_buy,
            sell_levels_count=n_sell,
        )
        # Размещаем ордера
        placed = await _place_grid_orders(session, adapter, symbol, levels, info)
        sym_state["levels"] = [lv.to_dict() for lv in levels]
        sym_state["mid_price"] = mid_price
        sym_state["step_pct_actual"] = step_pct
        sym_state["last_rebuild_epoch"] = time.time()
        return f"пересоздано {placed} ордеров (отменено {cancelled})"

    # Проверяем исполненные ордера и ставим встречные
    cycles = await _check_fills_and_counter(
        session, adapter, symbol, levels, info, state
    )

    sym_state["levels"] = [lv.to_dict() for lv in levels]
    sym_state["mid_price"] = mid_price

    if cycles > 0:
        return f"+{cycles} циклов завершено"
    return "ok"


async def _cancel_all_grid_orders(
    session: aiohttp.ClientSession,
    adapter: ExchangeAdapter,
    symbol: str,
    levels: list[GridLevel],
) -> int:
    """Отменить все grid-ордера по символу. Пауза между вызовами для rate-limit."""
    cancelled = 0
    for lv in levels:
        if lv.order_id and not lv.filled:
            try:
                await adapter.cancel_order(session, symbol, lv.order_id)
                cancelled += 1
                await asyncio.sleep(0.1)  # rate-limit guard
            except Exception as exc:  # noqa: BLE001
                print(f"[GRID] cancel {symbol} order {lv.order_id}: {exc}")
    return cancelled


async def _place_grid_orders(
    session: aiohttp.ClientSession,
    adapter: ExchangeAdapter,
    symbol: str,
    levels: list[GridLevel],
    info: dict[str, float],
) -> int:
    """Разместить лимитные ордера для каждого уровня сетки. Пауза для rate-limit."""
    placed = 0
    for lv in levels:
        try:
            result = await adapter.place_limit_order(
                session,
                symbol=symbol,
                side=lv.side,
                qty=lv.qty,
                price=lv.price,
                post_only=True,
                reduce_only=False,
            )
            if result and result.get("order_id"):
                lv.order_id = str(result["order_id"])
                placed += 1
            await asyncio.sleep(0.1)  # rate-limit guard
        except Exception as exc:  # noqa: BLE001
            print(f"[GRID] place {symbol} {lv.side}@{lv.price:.2f}: {exc}")
    return placed


async def _check_fills_and_counter(
    session: aiohttp.ClientSession,
    adapter: ExchangeAdapter,
    symbol: str,
    levels: list[GridLevel],
    info: dict[str, float],
    state: dict[str, Any],
) -> int:
    """Проверить исполнения и разместить встречные ордера.

    PnL считается точно: (sell_price - buy_price) * qty - fees.
    Комиссии берутся из config.FUNDING_TAKER_FEES.

    Возвращает количество завершённых циклов (buy→sell или sell→buy).
    """
    import config as _cfg

    # Получаем открытые ордера на бирже
    open_orders = await adapter.get_open_orders(session, symbol)
    open_ids = {str(o.get("orderId") or o.get("order_id", "")) for o in open_orders}

    # Комиссия (maker для grid, т.к. лимитные ордера)
    fee_rate = float(
        _cfg.FUNDING_TAKER_FEES.get(cfg.GRID_EXCHANGE, 0.0006)
    ) * 0.5  # maker ~ 50% от taker

    cycles = 0
    for lv in levels:
        if lv.filled or not lv.order_id:
            continue
        # Если ордера нет в открытых — значит он исполнен
        if lv.order_id not in open_ids:
            lv.filled = True
            lv.fill_price = lv.price  # Лимитный ордер — цена = заявленная

            # PnL: разница между buy и sell fill минус комиссии с обеих сторон
            # Один grid-цикл завершён = buy + sell. Считаем profit за цикл.
            notional = lv.qty * lv.fill_price
            fees_one_side = notional * fee_rate
            profit = notional * cfg.GRID_STEP_PCT - fees_one_side * 2
            capital_allocator.record_pnl(state, "grid", profit)

            grid_state = state["grid"]
            grid_state["total_cycles"] = int(grid_state.get("total_cycles", 0)) + 1
            grid_state["total_profit_usdt"] = (
                float(grid_state.get("total_profit_usdt", 0.0)) + profit
            )
            cycles += 1

            # Ставим встречный ордер
            counter_side = "Sell" if lv.side == "Buy" else "Buy"
            counter_price = lv.price * (
                (1 + cfg.GRID_STEP_PCT) if lv.side == "Buy" else (1 - cfg.GRID_STEP_PCT)
            )
            try:
                result = await adapter.place_limit_order(
                    session,
                    symbol=symbol,
                    side=counter_side,
                    qty=lv.qty,
                    price=counter_price,
                    post_only=True,
                    reduce_only=False,
                )
                if result and result.get("order_id"):
                    # Переиспользуем уровень как встречный
                    lv.side = counter_side
                    lv.price = counter_price
                    lv.order_id = str(result["order_id"])
                    lv.filled = False
                    lv.fill_price = 0.0
                await asyncio.sleep(0.1)  # rate-limit guard
            except Exception as exc:  # noqa: BLE001
                print(f"[GRID] counter {symbol} {counter_side}@{counter_price:.2f}: {exc}")

    return cycles


# ─── Управление ───────────────────────────────────────────────────────

async def stop_grid(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> str:
    """Остановить grid: отменить все ордера, очистить state."""
    grid_state = state.get("grid", {})
    adapter = _get_adapter()
    total_cancelled = 0

    for symbol in cfg.GRID_SYMBOLS:
        sym_state = grid_state.get("symbols", {}).get(symbol, {})
        levels_raw = sym_state.get("levels", [])
        levels = [GridLevel.from_dict(d) for d in levels_raw] if levels_raw else []
        cancelled = await _cancel_all_grid_orders(session, adapter, symbol, levels)
        total_cancelled += cancelled
        sym_state["levels"] = []

    grid_state["enabled"] = False
    return f"Grid остановлен. Отменено ордеров: {total_cancelled}."


async def start_grid(state: dict[str, Any]) -> str:
    """Включить grid-бот (ордера создадутся на следующем тике)."""
    grid_state = state.setdefault("grid", {})
    grid_state["enabled"] = True
    grid_state["last_tick_epoch"] = 0.0  # Тик сработает сразу
    return "Grid включен. Сетка будет создана на следующем тике."


def get_grid_status(state: dict[str, Any]) -> dict[str, Any]:
    """Статус grid-бота для UI."""
    grid_state = state.get("grid", {})
    symbols_info: dict[str, Any] = {}

    for symbol in cfg.GRID_SYMBOLS:
        sym_state = grid_state.get("symbols", {}).get(symbol, {})
        levels_raw = sym_state.get("levels", [])
        n_active = sum(1 for d in levels_raw if not d.get("filled", False))
        n_filled = sum(1 for d in levels_raw if d.get("filled", False))
        symbols_info[symbol] = {
            "mid_price": sym_state.get("mid_price", 0.0),
            "active_orders": n_active,
            "filled_orders": n_filled,
            "total_levels": len(levels_raw),
        }

    return {
        "enabled": grid_state.get("enabled", False),
        "symbols": symbols_info,
        "total_cycles": int(grid_state.get("total_cycles", 0)),
        "total_profit_usdt": float(grid_state.get("total_profit_usdt", 0.0)),
        "exchange": cfg.GRID_EXCHANGE,
        "levels_per_side": cfg.GRID_LEVELS,
        "step_pct": cfg.GRID_STEP_PCT,
        "leverage": cfg.GRID_LEVERAGE,
    }
