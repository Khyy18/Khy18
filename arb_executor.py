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

import asyncio
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
    slippage_buffer: Optional[float] = None,
) -> float:
    """Определить qty в базовой валюте, валидное на ОБЕИХ биржах.

    Алгоритм:
      qty_target = notional / mark_price * (1 - slippage_buffer)
      q_long = long_adapter.validate_and_round_qty(qty_target, long_info, mark)
      q_short = short_adapter.validate_and_round_qty(qty_target, short_info, mark)
      qty_final = min(q_long, q_short)

    Берём минимум, чтобы оба адаптера приняли заявку без округления вниз
    на одной из сторон (иначе получим не дельта-нейтрально).

    slippage_buffer (доля от 0 до 1, например 0.001 = 0.1%) — резерв на
    slippage при PostOnly→Market IOC fallback и округление вниз к qtyStep.
    Уменьшаем qty_target ДО валидации, чтобы реальный fill точно
    уложился в margin_required и не вызвал rejected на одной из ног.
    Если None — берём из config.ARB_SLIPPAGE_BUFFER (дефолт 0.001).

    Возвращает 0.0 если хотя бы один адаптер сказал "0" - не торгуем.
    """
    if mark_price <= 0:
        return 0.0
    if slippage_buffer is None:
        slippage_buffer = float(getattr(config, "ARB_SLIPPAGE_BUFFER", 0.001) or 0.0)
    # Защита от мусорных значений (отрицательных или >=1).
    if slippage_buffer < 0 or slippage_buffer >= 1:
        slippage_buffer = 0.0
    qty_target = (notional_usdt / mark_price) * (1.0 - slippage_buffer)

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

def _select_candidates(
    snapshots: dict[str, list[Any]],
    min_net_apr: float,
    allowed_symbols: Optional[list[str]] = None,
    excluded_symbols: Optional[set[str]] = None,
    limit: int = 5,
) -> list[Any]:
    """Вернуть топ-N CrossPair с применением фильтров.

    Возвращает список (а не первый) — вызывающий код применяет более
    дорогие фильтры (liquidity, pre-funding bonus, per-exchange cap)
    и берёт первый прошедший.

    Сортировка: по net_edge_apr * pre_funding_bonus (бонус за близость
    к funding-tick на SHORT-ноге).
    """
    pairs = arbitrage_engine.cross_exchange_pairs(
        snapshots, min_edge_apr=min_net_apr
    )
    if not pairs:
        return []
    if allowed_symbols:
        pairs = [p for p in pairs if p.symbol in allowed_symbols]
    if excluded_symbols:
        pairs = [p for p in pairs if p.symbol not in excluded_symbols]
    if not pairs:
        return []
    # Скоринг с pre-funding бонусом + ML direction multiplier.
    # ML-фактор bounded в [0.8, 1.3] и не является gate'ом — даже если
    # модель сломана/отсутствует, скоринг продолжает работать через
    # graceful fallback (multiplier=1.0). Сохраняем оригинальный порядок
    # при равных скорах через стабильную сортировку.
    def _score(p):
        score = p.net_edge_apr * _pre_funding_bonus(p)
        # ML direction multiplier — bounded в [0.8, 1.3], не gate.
        try:
            import funding_predictor
            import funding_history as _fh
            model = funding_predictor.load_model("funding_predictor_model.json")
            if model is not None:
                # Получаем history для SHORT-ноги (та, что получает funding).
                short_history = _fh.get_recent_for_symbol_exchange(
                    p.short_leg.exchange, p.symbol, hours=25,
                )
                features = funding_predictor.extract_features(short_history)
                if features is not None:
                    delta = funding_predictor.predict_delta(features, model)
                    if delta is not None:
                        multiplier = funding_predictor.to_multiplier(
                            delta, p.short_leg.funding_rate,
                        )
                        score *= multiplier
        except Exception:
            # ML недоступен или сломан — без multiplier'а, скоринг
            # продолжает работать как раньше.
            pass
        return score

    pairs_scored = [(p, _score(p)) for p in pairs]
    pairs_scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in pairs_scored[:max(1, limit)]]


def _select_candidate(
    snapshots: dict[str, list[Any]],
    min_net_apr: float,
    allowed_symbols: Optional[list[str]] = None,
    excluded_symbols: Optional[set[str]] = None,
) -> Optional[Any]:
    """Backward-compat обёртка: первый кандидат или None."""
    cands = _select_candidates(
        snapshots, min_net_apr, allowed_symbols, excluded_symbols, limit=1
    )
    return cands[0] if cands else None


def _per_exchange_leg_count(active_positions: list[dict[str, Any]]) -> dict[str, int]:
    """Сколько ног на каждой бирже сейчас открыто (LONG + SHORT суммарно).

    Используется для ARB_MAX_LEGS_PER_EXCHANGE: на одной бирже не больше
    N одновременно открытых ног, чтобы не концентрировать риск/маржу.
    """
    out: dict[str, int] = {}
    for p in active_positions:
        for k in ("long_exchange", "short_exchange"):
            ex = str(p.get(k, "")).lower()
            if ex:
                out[ex] = out.get(ex, 0) + 1
    return out


async def _check_liquidity(
    session: "Any",
    long_adapter: Any,
    short_adapter: Any,
    long_ex: str,
    short_ex: str,
    symbol: str,
    notional_usdt: float,
) -> tuple[bool, str]:
    """Проверка стакана перед открытием. Возвращает (ok, reason).

    Идея: на обеих биржах смотрим best_bid/best_ask, считаем mid и spread.
    Если spread > MAX_SPREAD_BPS — отказываем (slippage съест edge).

    Полный depth-анализ требует другого endpoint'а; на MVP-этапе spread
    — самый дешёвый и информативный сигнал ликвидности.
    """
    max_spread_bps = float(getattr(config, "ARB_MAX_SPREAD_BPS", 15.0))
    if max_spread_bps <= 0:
        return True, ""  # check выключен

    async def _spread_one(adapter: Any, ex_name: str) -> Optional[float]:
        try:
            ob = await adapter.get_orderbook_top(session, symbol)
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] orderbook_top({ex_name}/{symbol}): {exc}")
            return None
        if not ob:
            return None
        try:
            bid, ask = float(ob[0]), float(ob[1])
        except (TypeError, ValueError, IndexError):
            return None
        if bid <= 0 or ask <= 0 or ask <= bid:
            return None
        mid = (bid + ask) / 2.0
        return (ask - bid) / mid * 10000.0

    long_spread = await _spread_one(long_adapter, long_ex)
    short_spread = await _spread_one(short_adapter, short_ex)

    if long_spread is None or short_spread is None:
        # Если стакан недоступен — пропускаем (не открываем). Лучше
        # упустить сделку, чем войти на тонком рынке вслепую.
        return False, (
            f"orderbook_unavailable long={long_spread} short={short_spread}"
        )

    if long_spread > max_spread_bps or short_spread > max_spread_bps:
        return False, (
            f"spread_too_wide long={long_spread:.1f}bps short={short_spread:.1f}bps "
            f"> max={max_spread_bps:.1f}bps"
        )

    return True, f"long={long_spread:.1f}bps short={short_spread:.1f}bps"


def _pre_funding_bonus(cand: Any) -> float:
    """Бонус-множитель к скорингу кандидата по близости funding-tick.

    Логика: SHORT-нога зарабатывает funding в момент следующего tick'а.
    Если до tick'а < 30 минут — мы получим выплату почти сразу после
    открытия. Если только что прошёл — ждать 7+ часов до следующего.
    Возвращаем множитель 0.7..1.5.
    """
    bonus_window_min = float(getattr(config, "ARB_PREFUNDING_BONUS_WINDOW_MIN", 30.0))
    if bonus_window_min <= 0:
        return 1.0
    try:
        next_ts = int(cand.short_leg.next_funding_ts or 0)
    except (TypeError, ValueError, AttributeError):
        return 1.0
    if next_ts <= 0:
        return 1.0
    now_ms = int(time.time() * 1000)
    minutes_to_next = (next_ts - now_ms) / 60000.0
    if minutes_to_next <= 0 or minutes_to_next > 24 * 60:
        return 1.0
    if minutes_to_next < bonus_window_min:
        # Скоро funding — бонус линейно от 1.5 (на t=0) до 1.0 (на t=window).
        ratio = 1.0 - (minutes_to_next / bonus_window_min)
        return 1.0 + 0.5 * ratio
    # Только что прошёл funding (long-window до следующего) — лёгкий malus.
    interval_h = float(getattr(cand.short_leg, "interval_hours", 8.0)) or 8.0
    interval_min = interval_h * 60.0
    if minutes_to_next > interval_min - bonus_window_min:
        # Только что прошёл funding — ждать почти весь интервал. Снижаем.
        return 0.85
    return 1.0


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

    # Мульти-позиция: проверяем кол-во открытых и исключаем уже занятые символы.
    active_positions = arb_storage.get_all_active()
    max_positions = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    if len(active_positions) >= max_positions:
        return None
    used_symbols: set[str] = {p["symbol"] for p in active_positions}

    min_net_apr = float(getattr(config, "ARB_OPEN_MIN_NET_APR", 0.20))
    allowed = list(getattr(config, "ARB_ALLOWED_SYMBOLS", []))
    cands = _select_candidates(
        snapshots, min_net_apr, allowed or None,
        excluded_symbols=used_symbols, limit=8,
    )
    if not cands:
        return None

    # Per-exchange leg cap: не более N ног на одной бирже одновременно.
    legs_per_ex = _per_exchange_leg_count(active_positions)
    max_legs_per_ex = int(getattr(config, "ARB_MAX_LEGS_PER_EXCHANGE", 2))

    # Применяем все скоры и фильтры. Берём первого, кто прошёл.
    cand = None
    for c in cands:
        long_ex_test = c.long_leg.exchange.lower()
        short_ex_test = c.short_leg.exchange.lower()

        # Per-exchange cap.
        if max_legs_per_ex > 0:
            if legs_per_ex.get(long_ex_test, 0) >= max_legs_per_ex:
                print(
                    f"[ARB-EXEC] {c.symbol}: skip — {long_ex_test} уже имеет "
                    f"{legs_per_ex[long_ex_test]} ног (max={max_legs_per_ex})"
                )
                continue
            if legs_per_ex.get(short_ex_test, 0) >= max_legs_per_ex:
                print(
                    f"[ARB-EXEC] {c.symbol}: skip — {short_ex_test} уже имеет "
                    f"{legs_per_ex[short_ex_test]} ног (max={max_legs_per_ex})"
                )
                continue

        # Anti-spike: если средний funding-APR за последние 24ч сильно ниже
        # текущего spot — это спайк, входить рискованно.
        try:
            import funding_history
            spike = funding_history.is_spike(
                c.long_leg.exchange, c.symbol, c.long_leg.apr,
                c.short_leg.exchange, c.short_leg.apr,
            )
            if spike:
                print(
                    f"[ARB-EXEC] {c.symbol}: skip — funding spike detected "
                    f"(текущий APR сильно выше realized 24h)"
                )
                continue
        except Exception:  # noqa: BLE001
            pass  # модуль ещё не накопил истории — пропускаем фильтр

        # Blacklist по биржевым announcement'ам (delisting/maintenance).
        # Если хоть одна нога — на бирже, у которой висит активный blacklist
        # для этого символа, пропускаем кандидата.
        try:
            import runtime_state, announcement_monitor
            state_global = runtime_state.get_state()
            if state_global is not None:
                if (announcement_monitor.is_blacklisted(long_ex_test, c.symbol, state_global)
                        or announcement_monitor.is_blacklisted(short_ex_test, c.symbol, state_global)):
                    print(f"[ARB-EXEC] {c.symbol}: blacklist по announcement, пропуск")
                    continue
        except Exception:  # noqa: BLE001
            # любая ошибка импорта/чтения state — graceful, не блокируем вход
            pass

        cand = c
        break

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

    # Liquidity check: проверяем, что spread на обеих биржах в пределах
    # ARB_MAX_SPREAD_BPS. Защита от тонких книг (slippage съест edge).
    liq_ok, liq_reason = await _check_liquidity(
        session, long_adapter, short_adapter,
        long_ex, short_ex, cand.symbol, 0.0,
    )
    if not liq_ok:
        print(f"[ARB-EXEC] {cand.symbol}: liquidity reject — {liq_reason}")
        return None
    if liq_reason:
        print(f"[ARB-EXEC] {cand.symbol}: liquidity ok — {liq_reason}")

    # Проверка балансов: на каждой бирже достаточно ARB_NOTIONAL_USDT/leverage.
    # leverage здесь только для проверки достаточности, ордера ставим без
    # явного leverage - используется default настроенный на бирже.
    # notional подбирается по tier'у символа (стабильности funding-истории),
    # см. _get_tier_notional. Если истории нет — полный ARB_NOTIONAL_USDT.
    notional_usdt = _get_tier_notional(cand.symbol)
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

    # АТОМАРНОЕ ОТКРЫТИЕ через asyncio.gather. Раньше код шёл последовательно
    # (сначала LONG, потом SHORT) — между filled-LONG и attempt-SHORT проходило
    # 5-15 секунд, за которые цена могла уйти на 0.3-0.5%. Теперь обе ноги
    # стартуют одновременно. Если одна нога не fill за timeout — закрываем
    # успевшую через reduce-only.
    open_timeout = float(getattr(config, "ARB_OPEN_TIMEOUT_SEC", 12.0))

    async def _safe_open(adapter: Any, side: str, label: str):
        try:
            return await asyncio.wait_for(
                _open_leg(session, adapter, cand.symbol, side, qty_base, label),
                timeout=open_timeout,
            )
        except asyncio.TimeoutError:
            print(f"[ARB-EXEC] {label} тайм-аут {open_timeout:.0f}с")
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] {label} unexpected: {exc}")
            return None

    long_task = asyncio.create_task(
        _safe_open(long_adapter, "Buy", f"LONG@{long_ex}")
    )
    short_task = asyncio.create_task(
        _safe_open(short_adapter, "Sell", f"SHORT@{short_ex}")
    )
    long_fill, short_fill = await asyncio.gather(long_task, short_task)

    # Логика обработки: рассматриваем все 4 комбинации (LONG ok/fail × SHORT ok/fail).
    if not long_fill and not short_fill:
        print("[ARB-EXEC] Обе ноги не открылись")
        if notify:
            try:
                await notify(
                    f"⚠️ ARB: обе ноги {cand.symbol} не открыты "
                    f"(LONG@{long_ex} / SHORT@{short_ex}). Позиция не создана."
                )
            except Exception:  # noqa: BLE001
                pass
        return None

    if long_fill and not short_fill:
        # Открылась только LONG — откатываем reduce-only.
        print(f"[ARB-EXEC] SHORT не открыт — откатываем LONG@{long_ex}")
        rb = await _close_leg(
            session, long_adapter, cand.symbol, "Buy", qty_base,
            f"ROLLBACK LONG@{long_ex}",
        )
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
                rb_msg = "закрыт reduce-only" if rb else "НЕ закрыт — проверьте вручную!"
                await notify(
                    f"❌ ARB: SHORT@{short_ex} не открыт. LONG@{long_ex} {rb_msg}"
                )
            except Exception:  # noqa: BLE001
                pass
        return None

    if short_fill and not long_fill:
        # Открылась только SHORT — откатываем reduce-only.
        print(f"[ARB-EXEC] LONG не открыт — откатываем SHORT@{short_ex}")
        rb = await _close_leg(
            session, short_adapter, cand.symbol, "Sell", qty_base,
            f"ROLLBACK SHORT@{short_ex}",
        )
        arb_id = arb_storage.insert_open(
            symbol=cand.symbol,
            long_exchange=long_ex,
            short_exchange=short_ex,
            qty_base=qty_base,
            long_entry=0.0,
            short_entry=short_fill["fill_price"],
            long_order_id=None,
            short_order_id=short_fill["order_id"],
            edge_apr_open=cand.net_edge_apr,
            notional_usdt=notional_usdt,
            fees_estimate=fees,
        )
        if arb_id:
            arb_storage.mark_failed(arb_id, "long-leg-failed-and-short-rolled-back")
        if notify:
            try:
                rb_msg = "закрыт reduce-only" if rb else "НЕ закрыт — проверьте вручную!"
                await notify(
                    f"❌ ARB: LONG@{long_ex} не открыт. SHORT@{short_ex} {rb_msg}"
                )
            except Exception:  # noqa: BLE001
                pass
        return None

    # Обе ноги открыты успешно. Считаем slippage между ногами для аудита.
    slip_bps = abs(long_fill["fill_price"] - short_fill["fill_price"]) / max(
        (long_fill["fill_price"] + short_fill["fill_price"]) / 2.0, 1e-9
    ) * 10000.0
    print(
        f"[ARB-EXEC] Обе ноги filled: long={long_fill['fill_price']:.4f} "
        f"short={short_fill['fill_price']:.4f} slip={slip_bps:.1f} bps"
    )
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


# --- Multi-tier sizing --------------------------------------------------

def _get_tier_notional(symbol: str) -> float:
    """Подобрать notional для конкретного символа по его funding-истории.

    Логика:
      1. Берём funding_snapshots за 30 дней по этому символу (все биржи).
      2. Если данных нет / таблица отсутствует — возвращаем
         config.ARB_NOTIONAL_USDT (полный размер, безопасный fallback).
      3. Считаем cv = std_funding_rate / |mean_funding_rate|.
      4. Маппинг:
         - cv < 0.30 и n_obs > 200 → tier_a → ARB_NOTIONAL_TIER_A (400)
         - cv < 0.60                → tier_b → ARB_NOTIONAL_TIER_B (200)
         - иначе                    → tier_c → ARB_NOTIONAL_TIER_C (100)

    Идея: для стабильных символов (BTC/ETH) можно класть больше капитала,
    для волатильных funding-серий — меньше. Если истории мало — фолбэк
    к ARB_NOTIONAL_USDT (читай: пользователь не накопил данных, лучше не
    раздувать риск тиром, а взять консервативный default).

    Все ошибки SQLite/импорта ловим — возвращаем ARB_NOTIONAL_USDT.
    Тиковая функция не должна падать из-за БД.
    """
    fallback = float(getattr(config, "ARB_NOTIONAL_USDT", 200.0))
    try:
        import sqlite3
        import statistics
        from datetime import datetime, timedelta, timezone
        import memory  # для DB_PATH
    except Exception as exc:  # noqa: BLE001
        print(f"[TIER] import fail: {exc}, fallback={fallback}")
        return fallback

    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat(
        timespec="seconds"
    )
    try:
        with sqlite3.connect(memory.DB_PATH) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='funding_snapshots'"
            ).fetchone()
            if not row:
                return fallback
            rows = conn.execute(
                "SELECT rate FROM funding_snapshots "
                "WHERE symbol = ? AND ts >= ?",
                (symbol, cutoff),
            ).fetchall()
    except sqlite3.Error as exc:
        print(f"[TIER] sqlite fail для {symbol}: {exc}, fallback={fallback}")
        return fallback

    if not rows:
        return fallback

    rates = [float(r[0]) for r in rows if r[0] is not None]
    n_obs = len(rates)
    if n_obs < 2:
        return fallback

    mean_rate = sum(rates) / n_obs
    try:
        std_rate = statistics.stdev(rates)
    except statistics.StatisticsError:
        std_rate = 0.0

    if abs(mean_rate) < 1e-12:
        # Funding в среднем близок к нулю — символ не интересен,
        # но fallback к default размеру (не к tier_c, чтобы не путать
        # пользователя). Историческая логика: cv → inf, что попало бы
        # в tier_c, но математически это плохой сигнал, лучше default.
        return fallback

    cv = std_rate / abs(mean_rate)

    tier_a = float(getattr(config, "ARB_NOTIONAL_TIER_A", 400.0))
    tier_b = float(getattr(config, "ARB_NOTIONAL_TIER_B", 200.0))
    tier_c = float(getattr(config, "ARB_NOTIONAL_TIER_C", 100.0))

    if cv < 0.30 and n_obs > 200:
        print(f"[TIER] {symbol}: tier_a (cv={cv:.2f}, n={n_obs}) → {tier_a:.0f}")
        return tier_a
    if cv < 0.60:
        print(f"[TIER] {symbol}: tier_b (cv={cv:.2f}, n={n_obs}) → {tier_b:.0f}")
        return tier_b
    print(f"[TIER] {symbol}: tier_c (cv={cv:.2f}, n={n_obs}) → {tier_c:.0f}")
    return tier_c


async def monitor_and_maybe_close(
    session: "Any",
    adapters: dict[str, Any],
    snapshots: dict[str, list[Any]],
    notify: Optional[callable] = None,
) -> bool:
    """Для КАЖДОЙ активной позиции проверить условия закрытия и закрыть при
    необходимости. Возвращает True, если хотя бы одна позиция была закрыта.

    Условия закрытия (применяются к каждой паре независимо):
      1. Directional stop-loss: непосредственный убыток по двум ногам
         > ARB_DIRECTIONAL_STOP_PCT * notional. Защита от каскадных
         ликвидаций — funding-edge может всё ещё быть положительным,
         но цена ушла так, что мы попадаем под margin-call.
      2. Margin guard: на любой из двух бирж margin_ratio превысил
         ARB_MARGIN_RATIO_GUARD. Превентивное закрытие до ликвидации.
      3. Текущий net_edge_apr <= ARB_CLOSE_NET_APR.
      4. Время жизни > ARB_MAX_HOLD_HOURS.
      5. config.ARB_EXECUTOR_ENABLED стал False.
    """
    positions = arb_storage.get_all_active()
    if not positions:
        return False

    close_threshold = float(getattr(config, "ARB_CLOSE_NET_APR", 0.05))
    max_hold_h = float(getattr(config, "ARB_MAX_HOLD_HOURS", 168.0))
    dir_stop_pct = float(getattr(config, "ARB_DIRECTIONAL_STOP_PCT", 0.03))
    margin_guard = float(getattr(config, "ARB_MARGIN_RATIO_GUARD", 0.70))
    any_closed = False

    for pos in positions:
        # Если прошлый цикл начал закрытие но не завершил — дожимаем.
        if pos.get("status") == "CLOSING":
            closed = await _force_close(
                session, adapters, pos, "retry-closing", notify
            )
            any_closed = any_closed or closed
            continue

        # Условие 1: directional stop-loss.
        # Берём mark price с обеих бирж из snapshot и считаем "если бы
        # закрыли прямо сейчас — какой directional PnL". Если хуже
        # порога — закрываем превентивно.
        try:
            long_snap = _find_snap(snapshots, pos["long_exchange"], pos["symbol"])
            short_snap = _find_snap(snapshots, pos["short_exchange"], pos["symbol"])
            if long_snap and short_snap:
                qty = float(pos["qty_base"])
                long_entry = float(pos["long_entry"])
                short_entry = float(pos["short_entry"])
                hypo_dir_pnl = (
                    (long_snap.mark_price - long_entry) * qty
                    + (short_entry - short_snap.mark_price) * qty
                )
                notional = float(pos.get("notional_usdt") or 0.0)
                if notional > 0 and dir_stop_pct > 0:
                    loss_pct = -hypo_dir_pnl / notional  # положительное = убыток
                    if loss_pct >= dir_stop_pct:
                        closed = await _force_close(
                            session, adapters, pos,
                            f"directional_stop loss={loss_pct*100:.2f}% "
                            f">= {dir_stop_pct*100:.1f}% (pnl={hypo_dir_pnl:+.2f} "
                            f"USDT на notional={notional:.0f})",
                            notify,
                        )
                        any_closed = any_closed or closed
                        continue
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] directional_stop check fail: {exc}")

        # Условие 2: margin guard. Тяжёлая операция (RPC на биржу), поэтому
        # проверяем НЕ для каждой пары на каждом тике, а только если
        # последний check был > MARGIN_GUARD_INTERVAL_SEC секунд назад.
        # State хранится в самой записи pos, через arb_storage.update_kv
        # для простоты не выносим — используем in-memory лок на arb_id.
        if margin_guard > 0:
            should_close, reason_margin = await _check_margin_guard(
                session, adapters, pos, margin_guard
            )
            if should_close:
                closed = await _force_close(
                    session, adapters, pos, reason_margin, notify
                )
                any_closed = any_closed or closed
                continue

        # Условие 3: edge упал.
        edge = _current_edge_apr(
            snapshots, pos["symbol"], pos["long_exchange"], pos["short_exchange"]
        )
        if edge is not None and edge <= close_threshold:
            closed = await _force_close(
                session, adapters, pos,
                f"edge_decay edge={edge*100:.2f}% <= {close_threshold*100:.2f}%",
                notify,
            )
            any_closed = any_closed or closed
            continue

        # Условие 4: таймстоп.
        try:
            from datetime import datetime, timezone
            opened_dt = datetime.fromisoformat(str(pos.get("opened_ts") or ""))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            held_h = (datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600.0
        except Exception:  # noqa: BLE001
            held_h = 0.0
        if held_h >= max_hold_h:
            closed = await _force_close(
                session, adapters, pos,
                f"timestop {held_h:.1f}h >= {max_hold_h}h", notify,
            )
            any_closed = any_closed or closed
            continue

        # Условие 5: executor выключили из конфига.
        if not getattr(config, "ARB_EXECUTOR_ENABLED", False):
            closed = await _force_close(
                session, adapters, pos, "executor_disabled", notify,
            )
            any_closed = any_closed or closed

    return any_closed


# Кэш последней проверки margin по бирже: {exchange: (epoch, ratio)}.
# Не глобал в каноничном смысле, но процессно живёт.
_MARGIN_CACHE: dict[str, tuple[float, float]] = {}


async def _check_margin_guard(
    session: "Any",
    adapters: dict[str, Any],
    pos: dict[str, Any],
    threshold: float,
) -> tuple[bool, str]:
    """Дёргает balance/margin на обеих биржах позиции и возвращает True,
    если хотя бы у одной margin_ratio превысил threshold.

    Реализация компромиссная: единого "margin_ratio" в API адаптеров нет.
    Используем доступный сигнал: get_balance() возвращает свободный USDT.
    Если свободный < notional * (1 - threshold) / leverage — считаем
    margin критическим. Это проксирующая оценка, точная цифра требует
    отдельного метода в adapter (TODO: добавить get_account_info()).
    """
    cache_ttl = float(getattr(config, "MARGIN_GUARD_INTERVAL_SEC", 120.0))
    leverage = max(1.0, float(getattr(config, "ARB_LEVERAGE", 3.0)))
    notional = float(pos.get("notional_usdt") or 0.0)
    if notional <= 0:
        return False, ""

    margin_required = notional / leverage

    for ex_name in (pos["long_exchange"], pos["short_exchange"]):
        adapter = adapters.get(ex_name)
        if not adapter:
            continue

        cached = _MARGIN_CACHE.get(ex_name)
        now = time.time()
        if cached and (now - cached[0]) < cache_ttl:
            free_usdt = cached[1]
        else:
            try:
                free_usdt = await adapter.get_balance(session, "USDT")
            except Exception as exc:  # noqa: BLE001
                print(f"[ARB-EXEC] margin_guard get_balance({ex_name}): {exc}")
                continue
            if free_usdt is None:
                continue
            _MARGIN_CACHE[ex_name] = (now, float(free_usdt))

        # Если свободного USDT меньше чем (1-threshold)*margin_required —
        # значит margin занят больше чем threshold. Threshold 0.7 ⇒
        # триггерим если свободно < 0.3 * margin_required.
        if free_usdt < (1.0 - threshold) * margin_required:
            return True, (
                f"margin_guard {ex_name} free={free_usdt:.2f} < "
                f"{(1.0 - threshold) * margin_required:.2f} (threshold={threshold:.0%})"
            )

    return False, ""


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
    """Учёт funding-выплат для активных арб-пар.

    Стратегия:
      1. Сначала пытаемся честный учёт через adapter.get_funding_history():
         тянем все settlement-записи с момента last_funding_reconcile_ts
         (или opened_ts если первый раз) и суммируем реальные funding-USDT.
      2. Если адаптер не поддерживает (вернул []) — fallback на аналитическую
         оценку через snapshot (как раньше).

    Honest mode защищает от расхождений со снапшотом (rate мог скакнуть
    между сканами, или биржа считала по другому marker'у).
    """
    positions = arb_storage.get_all_active()
    if not positions:
        return

    for pos in positions:
        if pos.get("status") != "OPEN":
            continue

        sym = pos["symbol"]
        long_ex = pos["long_exchange"]
        short_ex = pos["short_exchange"]
        arb_id = int(pos["id"])
        notional = float(pos.get("notional_usdt") or 0.0)
        if notional <= 0:
            continue

        # Честный режим: берём реальные funding-выплаты с обеих бирж.
        honest_total = 0.0
        honest_used = False
        since_ms = _last_reconcile_ms(arb_id, pos)

        for ex_name in (long_ex, short_ex):
            adapter = adapters.get(ex_name)
            if not adapter:
                continue
            try:
                hist = await adapter.get_funding_history(
                    session, sym, since_ms=since_ms, limit=50,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[ARB-EXEC] get_funding_history({ex_name}/{sym}): {exc}")
                hist = []
            if not hist:
                continue
            honest_used = True
            for h in hist:
                try:
                    fund = float(h.get("funding") or 0.0)
                except (TypeError, ValueError):
                    continue
                # Биржа возвращает funding со знаком относительно нашей позиции:
                # положительный = получили, отрицательный = заплатили.
                # На LONG-ноге биржа знает что мы long, на SHORT-ноге — short.
                # Поэтому суммируем как есть, без переворачивания.
                honest_total += fund

        if honest_used:
            if abs(honest_total) > 1e-6:
                arb_storage.add_funding(arb_id, honest_total)
                print(
                    f"[ARB-EXEC] HONEST funding {honest_total:+.4f} USDT "
                    f"записано на arb #{arb_id}"
                )
            _set_last_reconcile_ms(arb_id, int(time.time() * 1000))
            continue

        # Fallback: аналитическая оценка через snapshot.
        long_snap = _find_snap(snapshots, long_ex, sym)
        short_snap = _find_snap(snapshots, short_ex, sym)
        if not long_snap or not short_snap:
            continue

        now_ms = int(time.time() * 1000)
        window_ms = 2 * float(getattr(config, "FUNDING_SCAN_INTERVAL_SEC", 300)) * 1000
        incremental = 0.0
        for snap, sign_for_us in [(long_snap, +1.0), (short_snap, -1.0)]:
            if snap.next_funding_ts and 0 < (now_ms - snap.next_funding_ts) < window_ms:
                incremental += -sign_for_us * snap.funding_rate * notional

        if abs(incremental) > 1e-6:
            arb_storage.add_funding(arb_id, incremental)
            print(
                f"[ARB-EXEC] ESTIMATED funding {incremental:+.4f} USDT "
                f"записано на arb #{arb_id} (биржи не вернули history)"
            )


# Кэш "когда последний раз сверялись funding-history" — на arb_id.
_LAST_RECONCILE_MS: dict[int, int] = {}


def _last_reconcile_ms(arb_id: int, pos: dict[str, Any]) -> int:
    """Когда в последний раз тянули funding-history. По умолчанию opened_ts."""
    if arb_id in _LAST_RECONCILE_MS:
        return _LAST_RECONCILE_MS[arb_id]
    try:
        from datetime import datetime
        opened_dt = datetime.fromisoformat(str(pos.get("opened_ts") or ""))
        return int(opened_dt.timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return 0


def _set_last_reconcile_ms(arb_id: int, ts_ms: int) -> None:
    _LAST_RECONCILE_MS[arb_id] = ts_ms


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
    """Отчёт по executor'у: все активные позиции, последние закрытия,
    кумулятив. Используется командой /arb_status."""
    enabled = bool(getattr(config, "ARB_EXECUTOR_ENABLED", False))
    enabled_str = "ON" if enabled else "OFF (read-only)"
    positions = arb_storage.get_all_active()
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    stats = arb_storage.get_total_stats()
    recent = arb_storage.get_recent_closed(5)

    lines = [
        "🤖 <b>ARB executor</b>",
        f"Статус: <b>{enabled_str}</b>",
        f"Открытых пар: <b>{len(positions)}/{max_pos}</b>",
    ]
    if not enabled:
        lines.append(
            "Включить: ARB_EXECUTOR_ENABLED=1 в .env и перезапустить бот."
        )

    if positions:
        from datetime import datetime, timezone
        for pos in positions:
            held_str = ""
            try:
                opened_dt = datetime.fromisoformat(str(pos["opened_ts"]))
                if opened_dt.tzinfo is None:
                    opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                held_h = (datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600
                held_str = f", {held_h:.1f}ч"
            except Exception:  # noqa: BLE001
                pass
            lines.append("")
            lines.append(
                f"<b>#{pos['id']} {pos['symbol']}</b> "
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
        lines.append("Активных позиций нет.")

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
