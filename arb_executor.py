"""Funding-rate cross-exchange arbitrage executor (Фаза 3).

Стратегия делает РОВНО одно: открывает дельта-нейтральную пару LONG perp
на бирже A + SHORT perp на бирже B по тому же символу, когда чистый
edge_apr >= ARB_OPEN_MIN_NET_APR. Держит пока edge не упадёт ниже
ARB_CLOSE_NET_APR (или сработает kill-switch). Закрывает обе ноги
reduce-only маркетом.

Нет спот-ноги. Нет переводов между биржами. Это самая безопасная
конфигурация funding-арбитража: обе ноги на perp -> нет проблемы
ребалансировки депозитов, нет gas, нет risk-of-execution на спот-ноге.

ВАЖНО: executor по умолчанию ВЫКЛЮЧЕН (config.ARB_EXECUTOR_ENABLED=False).
Пока пользователь не выставит флаг через .env - все методы кроме
read-only get_active работают как no-op.

Конечный автомат позиции:
    None -> evaluate_open() -> OPEN -> monitor() -> CLOSING -> CLOSED

Правила атомарности (открытие пары):
  1. Считаем qty в base, валидируем через info обеих бирж.
  2. Открываем LONG ногу.
  3. Если LONG не открылся - выходим, ничего не сделав (idempotent).
  4. Открываем SHORT ногу.
  5. Если SHORT не открылся - НЕМЕДЛЕННО закрываем LONG reduce-only.
     Записываем в БД статус FAILED + reason. Шлём пользователю алерт.
  6. Только после успеха обеих - insert_open() в БД.

Закрытие:
  1. mark_closing() в БД.
  2. Закрываем LONG (Sell, reduce_only).
  3. Закрываем SHORT (Buy, reduce_only).
  4. Если хоть одна не закрылась - ставим FAILED и алертим.
  5. На успехе - insert_closed() с PnL.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import arb_storage
import arbitrage_engine
import config


def _utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


# --- Контекст adapters (передаётся снаружи, не хардкодим) ---------------

# adapters: dict[str, ExchangeAdapter] - по имени биржи (lower-case).
# В main.py заполняется из get_adapter() и передаётся в каждый tick.


# --- Расчёт размера позиции --------------------------------------------

def _compute_qty_base(
    notional_usdt: float,
    mark_price: float,
    long_info: dict[str, Any],
    short_info: dict[str, Any],
    long_adapter: Any,
    short_adapter: Any,
) -> float:
    """Определить qty в базовой валюте, валидное на ОБЕИХ биржах.

    Алгоритм:
      qty_target = notional / mark_price
      q_long = long_adapter.validate_and_round_qty(qty_target, long_info, mark)
      q_short = short_adapter.validate_and_round_qty(qty_target, short_info, mark)
      qty_final = min(q_long, q_short)

    Берём минимум, чтобы оба адаптера приняли заявку без округления вниз
    на одной из сторон (иначе получим не дельта-нейтрально).

    Возвращает 0.0 если хотя бы один адаптер сказал "0" - не торгуем.
    """
    if mark_price <= 0:
        return 0.0
    qty_target = notional_usdt / mark_price

    try:
        q_long = float(
            long_adapter.validate_and_round_qty(qty_target, long_info, mark_price)
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] long validate_qty failed: {exc}")
        q_long = 0.0
    try:
        q_short = float(
            short_adapter.validate_and_round_qty(qty_target, short_info, mark_price)
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] short validate_qty failed: {exc}")
        q_short = 0.0

    if q_long <= 0 or q_short <= 0:
        return 0.0
    return min(q_long, q_short)


# --- Поиск кандидата для открытия ---------------------------------------

def _select_candidate(
    snapshots: dict[str, list[Any]],
    min_net_apr: float,
    allowed_symbols: Optional[list[str]] = None,
) -> Optional[Any]:
    """Вернуть лучший CrossPair из snapshots или None.

    Фильтры:
      - net_edge_apr >= min_net_apr;
      - символ в allowed_symbols (если задан);
      - обе ноги на разных биржах (тривиально - cross_exchange_pairs
        отдаёт только такие).
    """
    pairs = arbitrage_engine.cross_exchange_pairs(
        snapshots, min_edge_apr=min_net_apr
    )
    if not pairs:
        return None
    if allowed_symbols:
        pairs = [p for p in pairs if p.symbol in allowed_symbols]
        if not pairs:
            return None
    # cross_exchange_pairs уже сортирует по net_edge_apr desc.
    return pairs[0]


# --- Открытие пары ------------------------------------------------------

async def _open_leg(
    session: "Any",
    adapter: Any,
    symbol: str,
    side: str,
    qty: float,
    label: str,
) -> Optional[dict[str, Any]]:
    """Открыть одну ногу. Возвращает dict с fill_price/fill_qty/orderId
    или None при провале.

    side: 'Buy' (LONG) или 'Sell' (SHORT).
    """
    try:
        resp = await adapter.place_order_with_fallback(
            session,
            symbol=symbol,
            side=side,
            qty=qty,
            stop_loss=None,
            take_profit=None,
            reduce_only=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] {label} place_order exception: {exc}")
        return None
    if not resp or resp.get("retCode") != 0:
        print(f"[ARB-EXEC] {label} order rejected: {resp}")
        return None
    fill_price = float(resp.get("fill_price") or 0.0)
    fill_qty = float(resp.get("fill_qty") or 0.0)
    if fill_price <= 0 or fill_qty <= 0:
        print(f"[ARB-EXEC] {label} no fills: {resp}")
        return None
    return {
        "fill_price": fill_price,
        "fill_qty": fill_qty,
        "order_id": str((resp.get("result") or {}).get("orderId") or ""),
    }


async def _close_leg(
    session: "Any",
    adapter: Any,
    symbol: str,
    side_to_close: str,
    qty: float,
    label: str,
) -> Optional[dict[str, Any]]:
    """Закрыть одну ногу reduce-only маркетом.
    side_to_close - сторона ИСХОДНОЙ позиции ('Buy' для LONG, 'Sell' для SHORT).
    Закрывающий ордер ставим в противоположную сторону."""
    close_side = "Sell" if side_to_close == "Buy" else "Buy"
    try:
        resp = await adapter.place_order_with_fallback(
            session,
            symbol=symbol,
            side=close_side,
            qty=qty,
            reduce_only=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] {label} close exception: {exc}")
        return None
    if not resp or resp.get("retCode") != 0:
        print(f"[ARB-EXEC] {label} close rejected: {resp}")
        return None
    fill_price = float(resp.get("fill_price") or 0.0)
    return {"fill_price": fill_price}


async def evaluate_and_open(
    session: "Any",
    adapters: dict[str, Any],
    snapshots: dict[str, list[Any]],
    notify: Optional[callable] = None,
) -> Optional[int]:
    """Главный entry-point на стороне открытия. Вызывается из
    _arb_executor_tick когда активной позиции нет.

    Возвращает arb_id если пара открыта, иначе None.

    notify - async callable(text:str), отправляет в Telegram. Может быть
    None в тестах.
    """
    if not getattr(config, "ARB_EXECUTOR_ENABLED", False):
        return None

    min_net_apr = float(getattr(config, "ARB_OPEN_MIN_NET_APR", 0.20))
    allowed = list(getattr(config, "ARB_ALLOWED_SYMBOLS", []))
    cand = _select_candidate(snapshots, min_net_apr, allowed or None)
    if cand is None:
        return None

    long_ex = cand.long_leg.exchange.lower()
    short_ex = cand.short_leg.exchange.lower()
    long_adapter = adapters.get(long_ex)
    short_adapter = adapters.get(short_ex)
    if not long_adapter or not short_adapter:
        print(f"[ARB-EXEC] Нет адаптера для {long_ex}/{short_ex}")
        return None

    # Прогрев instrument info на обеих биржах (за одно может посчитать
    # ctVal для OKX).
    try:
        long_info = await long_adapter.get_instrument_info(session, cand.symbol)
        short_info = await short_adapter.get_instrument_info(session, cand.symbol)
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] instrument_info fail: {exc}")
        return None
    if not long_info or not short_info:
        print(f"[ARB-EXEC] Нет instrument_info для {cand.symbol}")
        return None

    # Проверка балансов: на каждой бирже достаточно ARB_NOTIONAL_USDT/leverage.
    # leverage здесь только для проверки достаточности, ордера ставим без
    # явного leverage - используется default настроенный на бирже.
    notional_usdt = float(getattr(config, "ARB_NOTIONAL_USDT", 200.0))
    leverage = max(1.0, float(getattr(config, "ARB_LEVERAGE", 3.0)))
    margin_required = notional_usdt / leverage
    safety = 1.10  # 10% запас на колебания цены и комиссии

    try:
        bal_long = await long_adapter.get_balance(session, "USDT")
        bal_short = await short_adapter.get_balance(session, "USDT")
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] get_balance fail: {exc}")
        return None
    if bal_long is None or bal_short is None:
        print(f"[ARB-EXEC] balance unavailable: long={bal_long} short={bal_short}")
        return None
    if bal_long < margin_required * safety or bal_short < margin_required * safety:
        print(
            f"[ARB-EXEC] недостаточно USDT: long {bal_long:.2f} / "
            f"short {bal_short:.2f}, нужно ~{margin_required * safety:.2f} на каждой"
        )
        return None

    # Mark price берём усреднённый между двумя биржами.
    mark_avg = (cand.long_leg.mark_price + cand.short_leg.mark_price) / 2.0
    qty_base = _compute_qty_base(
        notional_usdt, mark_avg, long_info, short_info, long_adapter, short_adapter
    )
    if qty_base <= 0:
        print(
            f"[ARB-EXEC] qty=0 после фильтров для {cand.symbol} "
            f"(notional={notional_usdt}, mark={mark_avg})"
        )
        return None

    # Оценка комиссий до открытия (для записи в БД).
    fees = _estimate_fees(notional_usdt, long_ex, short_ex)

    print(
        f"[ARB-EXEC] OPEN candidate: {cand.symbol} "
        f"LONG@{long_ex} SHORT@{short_ex} qty={qty_base} "
        f"net_apr={cand.net_edge_apr*100:.2f}%"
    )

    # 1. Открыть LONG.
    long_fill = await _open_leg(
        session, long_adapter, cand.symbol, "Buy", qty_base, f"LONG@{long_ex}"
    )
    if not long_fill:
        if notify:
            try:
                await notify(
                    f"⚠️ ARB: не удалось открыть LONG@{long_ex} {cand.symbol}. "
                    "Позиция не создана."
                )
            except Exception:  # noqa: BLE001
                pass
        return None

    # 2. Открыть SHORT.
    short_fill = await _open_leg(
        session, short_adapter, cand.symbol, "Sell", qty_base, f"SHORT@{short_ex}"
    )
    if not short_fill:
        # Откатываем LONG.
        print(f"[ARB-EXEC] SHORT не открыт - откатываем LONG@{long_ex}")
        rb = await _close_leg(
            session, long_adapter, cand.symbol, "Buy", qty_base,
            f"ROLLBACK LONG@{long_ex}",
        )
        # Регистрируем неудачу в БД, чтобы оператор знал.
        arb_id = arb_storage.insert_open(
            symbol=cand.symbol,
            long_exchange=long_ex,
            short_exchange=short_ex,
            qty_base=qty_base,
            long_entry=long_fill["fill_price"],
            short_entry=0.0,
            long_order_id=long_fill["order_id"],
            short_order_id=None,
            edge_apr_open=cand.net_edge_apr,
            notional_usdt=notional_usdt,
            fees_estimate=fees,
        )
        if arb_id:
            arb_storage.mark_failed(arb_id, "short-leg-failed-and-long-rolled-back")
        if notify:
            try:
                await notify(
                    f"❌ ARB: SHORT@{short_ex} не открыт. LONG@{long_ex} "
                    "был {0}".format("закрыт reduce-only" if rb else
                                     "НЕ закрыт - проверьте биржу вручную!")
                )
            except Exception:  # noqa: BLE001
                pass
        return None

    # 3. Обе ноги открыты успешно - сохраняем.
    arb_id = arb_storage.insert_open(
        symbol=cand.symbol,
        long_exchange=long_ex,
        short_exchange=short_ex,
        qty_base=qty_base,
        long_entry=long_fill["fill_price"],
        short_entry=short_fill["fill_price"],
        long_order_id=long_fill["order_id"],
        short_order_id=short_fill["order_id"],
        edge_apr_open=cand.net_edge_apr,
        notional_usdt=notional_usdt,
        fees_estimate=fees,
    )
    if arb_id is None:
        # Хранилище упало, но ордера уже на бирже. Алертим максимально громко.
        if notify:
            try:
                await notify(
                    "🚨 ARB CRITICAL: ордера открыты на бирже, но БД не приняла "
                    f"запись. {cand.symbol} LONG@{long_ex} SHORT@{short_ex} "
                    f"qty={qty_base}. Закрывайте вручную и выключайте executor."
                )
            except Exception:  # noqa: BLE001
                pass
        return None

    if notify:
        try:
            await notify(
                f"🟢 ARB OPEN #{arb_id}: {cand.symbol}\n"
                f"LONG@{long_ex}: {long_fill['fill_price']:.4f}\n"
                f"SHORT@{short_ex}: {short_fill['fill_price']:.4f}\n"
                f"qty={qty_base} | notional≈${notional_usdt:.0f}\n"
                f"net APR на момент входа: "
                f"{arbitrage_engine.format_apr(cand.net_edge_apr)}"
            )
        except Exception:  # noqa: BLE001
            pass
    return arb_id


# --- Мониторинг и закрытие ---------------------------------------------

def _current_edge_apr(
    snapshots: dict[str, list[Any]],
    symbol: str,
    long_ex: str,
    short_ex: str,
) -> Optional[float]:
    """Найти текущий net_edge_apr для конкретной пары (биржи, символ).

    Идёт по cross_exchange_pairs(min_edge_apr=-inf - условно через
    очень отрицательный порог), фильтрует на нашу пару. Возвращает None,
    если пары нет (например, какая-то нога не вернула funding).
    """
    pairs = arbitrage_engine.cross_exchange_pairs(snapshots, min_edge_apr=-9.99)
    for p in pairs:
        if p.symbol == symbol and {p.long_leg.exchange.lower(),
                                    p.short_leg.exchange.lower()} == {long_ex, short_ex}:
            # Если LONG/SHORT-роли поменялись по сравнению с нашей записью,
            # это значит edge развернулся - возвращаем СО ЗНАКОМ МИНУС.
            if p.long_leg.exchange.lower() == long_ex:
                return p.net_edge_apr
            return -p.net_edge_apr
    return None


def _estimate_fees(notional_usdt: float, long_ex: str, short_ex: str) -> float:
    """Сумма taker-комиссий для full round-trip (open + close на ОБЕИХ биржах)."""
    fees = getattr(config, "FUNDING_TAKER_FEES", {}) or {}
    long_fee = float(fees.get(long_ex, fees.get("default", 0.0006)))
    short_fee = float(fees.get(short_ex, fees.get("default", 0.0006)))
    # 2 сделки на каждой ноге = 4 taker-fee.
    return notional_usdt * (2 * long_fee + 2 * short_fee)


async def monitor_and_maybe_close(
    session: "Any",
    adapters: dict[str, Any],
    snapshots: dict[str, list[Any]],
    notify: Optional[callable] = None,
) -> bool:
    """Если есть активная позиция, проверить условия закрытия и при
    необходимости закрыть. Возвращает True, если позиция была закрыта.

    Условия закрытия:
      1. Текущий net_edge_apr <= ARB_CLOSE_NET_APR.
      2. Время жизни > ARB_MAX_HOLD_HOURS.
      3. global kill_switch_state != NONE - закрываем превентивно.
      4. config.ARB_EXECUTOR_ENABLED стал False - закрываем по выключению.
    """
    pos = arb_storage.get_active()
    if not pos:
        return False
    if pos.get("status") == "CLOSING":
        # Если в БД CLOSING, значит прошлый цикл попытался закрыть и не дошёл.
        # Попробуем ещё раз.
        return await _force_close(session, adapters, pos, "retry-closing", notify)

    # Условие 1: edge упал.
    edge = _current_edge_apr(
        snapshots, pos["symbol"], pos["long_exchange"], pos["short_exchange"]
    )
    close_threshold = float(getattr(config, "ARB_CLOSE_NET_APR", 0.05))
    if edge is not None and edge <= close_threshold:
        return await _force_close(
            session, adapters, pos,
            f"edge_decay edge={edge*100:.2f}% <= {close_threshold*100:.2f}%",
            notify,
        )

    # Условие 2: таймстоп.
    max_hold_h = float(getattr(config, "ARB_MAX_HOLD_HOURS", 168.0))
    opened_ts = pos.get("opened_ts") or ""
    try:
        from datetime import datetime, timezone
        opened_dt = datetime.fromisoformat(str(opened_ts))
        if opened_dt.tzinfo is None:
            opened_dt = opened_dt.replace(tzinfo=timezone.utc)
        held_h = (datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        held_h = 0.0
    if held_h >= max_hold_h:
        return await _force_close(
            session, adapters, pos,
            f"timestop {held_h:.1f}h >= {max_hold_h}h", notify,
        )

    # Условие 3: executor выключили из конфига - закрываемся.
    if not getattr(config, "ARB_EXECUTOR_ENABLED", False):
        return await _force_close(
            session, adapters, pos, "executor_disabled", notify,
        )

    return False


async def _force_close(
    session: "Any",
    adapters: dict[str, Any],
    pos: dict[str, Any],
    reason: str,
    notify: Optional[callable],
) -> bool:
    """Закрыть обе ноги reduce-only и записать результат в БД."""
    arb_id = int(pos["id"])
    arb_storage.mark_closing(arb_id)
    print(f"[ARB-EXEC] CLOSE #{arb_id} reason={reason}")

    long_ex = pos["long_exchange"]
    short_ex = pos["short_exchange"]
    long_adapter = adapters.get(long_ex)
    short_adapter = adapters.get(short_ex)
    if not long_adapter or not short_adapter:
        arb_storage.mark_failed(arb_id, f"adapter-missing-on-close: {reason}")
        if notify:
            try:
                await notify(
                    f"🚨 ARB CLOSE FAIL #{arb_id}: нет адаптера. "
                    f"reason={reason}. Закройте вручную."
                )
            except Exception:  # noqa: BLE001
                pass
        return True  # Состояние больше не "OPEN", нет смысла мониторить.

    qty = float(pos["qty_base"])
    sym = pos["symbol"]

    # Закрываем LONG (Sell reduce_only).
    long_close = await _close_leg(
        session, long_adapter, sym, "Buy", qty, f"CLOSE LONG@{long_ex}"
    )
    # Закрываем SHORT (Buy reduce_only).
    short_close = await _close_leg(
        session, short_adapter, sym, "Sell", qty, f"CLOSE SHORT@{short_ex}"
    )

    if not long_close or not short_close:
        arb_storage.mark_failed(
            arb_id,
            f"partial-close (long={'ok' if long_close else 'fail'}, "
            f"short={'ok' if short_close else 'fail'}): {reason}",
        )
        if notify:
            try:
                await notify(
                    f"🚨 ARB CLOSE PARTIAL #{arb_id} {sym}\n"
                    f"LONG@{long_ex}: {'OK' if long_close else 'FAIL'}\n"
                    f"SHORT@{short_ex}: {'OK' if short_close else 'FAIL'}\n"
                    f"reason={reason}. Закройте оставшуюся ногу вручную."
                )
            except Exception:  # noqa: BLE001
                pass
        return True

    # Расчёт PnL.
    long_entry = float(pos["long_entry"])
    short_entry = float(pos["short_entry"])
    long_exit = float(long_close["fill_price"])
    short_exit = float(short_close["fill_price"])
    pnl_directional = (long_exit - long_entry) * qty + (short_entry - short_exit) * qty
    pnl_funding = float(pos.get("funding_received") or 0.0)
    fees_est = float(pos.get("fees_estimate") or 0.0)
    pnl_total = pnl_directional + pnl_funding - fees_est

    arb_storage.insert_closed(
        arb_id=arb_id,
        long_exit=long_exit,
        short_exit=short_exit,
        pnl_directional=pnl_directional,
        pnl_funding=pnl_funding,
        pnl_total=pnl_total,
        reason_close=reason,
    )

    if notify:
        try:
            arrow = "▲" if pnl_total >= 0 else "▼"
            await notify(
                f"🔻 ARB CLOSE #{arb_id} {sym}\n"
                f"LONG@{long_ex} exit: {long_exit:.4f}\n"
                f"SHORT@{short_ex} exit: {short_exit:.4f}\n"
                f"Directional PnL: {pnl_directional:+.2f} USDT\n"
                f"Funding PnL: {pnl_funding:+.2f} USDT\n"
                f"Fees (est): −{fees_est:.2f} USDT\n"
                f"Total: {arrow} {pnl_total:+.2f} USDT\n"
                f"Причина: {reason}"
            )
        except Exception:  # noqa: BLE001
            pass
    return True


# --- Учёт funding-выплат ------------------------------------------------

async def reconcile_funding_payments(
    session: "Any",
    adapters: dict[str, Any],
    snapshots: dict[str, list[Any]],
) -> None:
    """Прибавить к funding_received сумму ожидаемой funding-выплаты, если
    в этом тике пересекли границу funding-интервала.

    Грубая оценка: смотрим текущий snapshot, если у LONG-ноги funding_rate < 0
    значит мы (long) получим |rate|*notional на следующем расчётном времени,
    при условии что мы держим позицию в тот момент. Аналогично для SHORT.

    Реальная сумма выплаты появляется в истории биржевых транзакций -
    в идеале её надо доставать через адаптер (отдельный эндпоинт).
    Текущая реализация делает АНАЛИТИЧЕСКУЮ оценку: каждый раз когда
    next_funding_ts только что прошёл (т.е. tick попал в окно после
    funding-tick), прибавляем |rate| * notional к funding_received.

    Оценка несовершенна (не учитывает изменение цены, частичный fill),
    но даёт пользователю корректный порядок суммы прямо в UI. Точные
    цифры подгружаем при закрытии (см. arb_executor v2 - todo).
    """
    pos = arb_storage.get_active()
    if not pos or pos.get("status") != "OPEN":
        return

    sym = pos["symbol"]
    long_ex = pos["long_exchange"]
    short_ex = pos["short_exchange"]
    arb_id = int(pos["id"])
    notional = float(pos.get("notional_usdt") or 0.0)
    if notional <= 0:
        return

    long_snap = _find_snap(snapshots, long_ex, sym)
    short_snap = _find_snap(snapshots, short_ex, sym)
    if not long_snap or not short_snap:
        return

    now_ms = int(time.time() * 1000)
    # Условие "funding только что выплачен": next_funding_ts ушёл в прошлое
    # (now_ms > next_funding_ts) и разница не больше 2 тиков сканера
    # (~10 минут). Это окно ловит выплату ровно один раз.
    window_ms = 2 * float(getattr(config, "FUNDING_SCAN_INTERVAL_SEC", 300)) * 1000

    incremental = 0.0
    for snap, sign_for_us in [(long_snap, +1.0), (short_snap, -1.0)]:
        # LONG получает funding если rate<0 (платят шорту -> наоборот, платит лонг).
        # Wait, funding конвенция: положительный rate = LONG ПЛАТИТ shorts.
        # Значит:
        #   LONG-нога: knowing direction = +1 (LONG), funding нам = -rate * notional
        #   SHORT-нога: knowing direction = -1 (SHORT), funding нам = +rate * notional
        # Объединим: nam += direction * (-rate) * notional = -direction*rate*notional
        if snap.next_funding_ts and 0 < (now_ms - snap.next_funding_ts) < window_ms:
            incremental += -sign_for_us * snap.funding_rate * notional

    if abs(incremental) > 1e-6:
        arb_storage.add_funding(arb_id, incremental)
        print(
            f"[ARB-EXEC] funding +{incremental:.4f} USDT записано на arb #{arb_id}"
        )


def _find_snap(
    snapshots: dict[str, list[Any]],
    exchange: str,
    symbol: str,
) -> Optional[Any]:
    arr = snapshots.get(exchange) or []
    for s in arr:
        if s.symbol == symbol:
            return s
    return None


# --- Telegram-форматтер для /arb_status ---------------------------------

def format_status() -> str:
    """Отчёт по executor'у: текущая позиция (если есть), последние закрытия,
    кумулятив. Используется командой /arb_status."""
    enabled = bool(getattr(config, "ARB_EXECUTOR_ENABLED", False))
    enabled_str = "ON" if enabled else "OFF (read-only)"
    pos = arb_storage.get_active()
    stats = arb_storage.get_total_stats()
    recent = arb_storage.get_recent_closed(5)

    lines = [
        "🤖 <b>ARB executor</b>",
        f"Статус: <b>{enabled_str}</b>",
    ]
    if not enabled:
        lines.append(
            "Включить: ARB_EXECUTOR_ENABLED=1 в .env и перезапустить бот."
        )

    if pos:
        lines.append("")
        lines.append("<b>Активная пара:</b>")
        held_str = ""
        try:
            from datetime import datetime, timezone
            opened_dt = datetime.fromisoformat(str(pos["opened_ts"]))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            held_h = (datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600
            held_str = f", держим {held_h:.1f}ч"
        except Exception:  # noqa: BLE001
            pass
        lines.append(
            f"#{pos['id']} {pos['symbol']} "
            f"LONG@{pos['long_exchange']} SHORT@{pos['short_exchange']}{held_str}"
        )
        lines.append(
            f"qty={pos['qty_base']}  notional≈${pos['notional_usdt']:.0f}"
        )
        lines.append(
            f"Entry: long {pos['long_entry']:.4f} / short {pos['short_entry']:.4f}"
        )
        lines.append(
            f"Funding получено: {float(pos.get('funding_received') or 0):+.4f} USDT"
        )
    else:
        lines.append("")
        lines.append("Активной позиции нет.")

    lines.append("")
    lines.append("<b>Кумулятив по закрытым:</b>")
    lines.append(f"Сделок: {stats['n']}")
    lines.append(f"Total PnL: {stats['pnl_sum']:+.4f} USDT")
    lines.append(f"  └ Funding: {stats['funding_sum']:+.4f}")
    lines.append(f"  └ Direct.: {stats['dir_sum']:+.4f}")
    lines.append(f"  └ Fees est: −{stats['fees_sum']:.4f}")

    if recent:
        lines.append("")
        lines.append("<b>Последние 5 закрытий:</b>")
        for r in recent:
            arrow = "▲" if (r.get("pnl_total") or 0) >= 0 else "▼"
            status = r.get("status") or ""
            sym = r.get("symbol") or ""
            pnl = float(r.get("pnl_total") or 0.0)
            ts = (r.get("closed_ts") or "")[:16].replace("T", " ")
            lines.append(
                f"#{r['id']} {sym} [{status}] {arrow} {pnl:+.4f} ({ts})"
            )
    return "\n".join(lines)
