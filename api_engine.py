"""Асинхронный коннектор Bybit V5 (Unified Trading Account).

Ручная подпись HMAC-SHA256 по спецификации Bybit V5:
    sign = HMAC_SHA256(
        key   = api_secret,
        data  = timestamp + api_key + recv_window + payload,
    ).hexdigest()

Где payload:
    - для GET  -> готовая URL-encoded строка query (в том порядке, в котором
      она будет отправлена в URL);
    - для POST -> точная JSON-строка тела запроса.

Все HTTP-вызовы обёрнуты в try/except: при сетевой/парс-ошибке функции
возвращают None или dict с описанием ошибки, а сама ошибка логируется
по-русски. Ни одна функция не пробрасывает исключение наружу, чтобы
транзиентные сбои не валили торговый цикл.

v2-доработки (Zenith-Control Ultimate):
    - get_instruments_info + кэш + validate_and_round_qty: фильтры биржи
      (minOrderQty, qtyStep, minNotionalValue, tickSize);
    - get_orderbook_top: best bid/ask для PostOnly-лимита;
    - get_open_orders / cancel_order: управление живыми лимитами;
    - place_market_order: Market IOC (переименование существующей логики);
    - place_post_only_limit: лимит с timeInForce=PostOnly;
    - place_order_with_fallback: PostOnly с timeout -> market IOC при
      недозаливе (с SL/TP на market-fallback);
    - place_order: тонкий wrapper над place_market_order (back-compat).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import time
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp

import config


def _now_ms() -> str:
    """Текущий timestamp в миллисекундах, строкой - как требует Bybit."""
    return str(int(time.time() * 1000))


def _sign(payload: str, timestamp: str) -> str:
    """HMAC-SHA256 подпись запроса. payload - либо query string, либо тело."""
    message = (timestamp + config.BYBIT_API_KEY + config.BYBIT_RECV_WINDOW + payload)
    return hmac.new(
        config.BYBIT_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _auth_headers(payload: str, timestamp: Optional[str] = None) -> dict[str, str]:
    """Собрать все заголовки аутентификации Bybit V5."""
    ts = timestamp or _now_ms()
    return {
        "X-BAPI-API-KEY": config.BYBIT_API_KEY,
        "X-BAPI-SIGN": _sign(payload, ts),
        "X-BAPI-SIGN-TYPE": "2",
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": config.BYBIT_RECV_WINDOW,
        "Content-Type": "application/json",
    }


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    params: Optional[dict[str, Any]] = None,
    body: Optional[dict[str, Any]] = None,
    auth: bool = False,
    timeout: int = 15,
) -> Optional[dict[str, Any]]:
    """Единая обёртка HTTP-запроса с обработкой ошибок и русским логом."""
    url = config.BYBIT_BASE_URL + path
    params = params or {}
    body = body or {}

    try:
        if method.upper() == "GET":
            query = urlencode(params) if params else ""
            full_url = f"{url}?{query}" if query else url
            headers = _auth_headers(query) if auth else {}
            async with session.get(full_url, headers=headers, timeout=timeout) as resp:
                text = await resp.text()
        elif method.upper() == "POST":
            body_str = json.dumps(body, separators=(",", ":"))
            headers = _auth_headers(body_str) if auth else {"Content-Type": "application/json"}
            async with session.post(url, data=body_str, headers=headers, timeout=timeout) as resp:
                text = await resp.text()
        else:
            print(f"[API] Неподдерживаемый HTTP метод: {method}")
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"[API] Не удалось распарсить ответ Bybit ({path}): {text[:200]}")
            return None
    except aiohttp.ClientError as exc:
        print(f"[API] Сетевая ошибка Bybit {path}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[API] Неожиданная ошибка запроса {path}: {exc}")
        return None


# --- Публичные методы API ---

async def get_server_time(session: aiohttp.ClientSession) -> Optional[dict[str, Any]]:
    """Публичный эндпоинт: серверное время Bybit (используем для пинга)."""
    return await _request(session, "GET", "/v5/market/time", auth=False)


async def get_klines(
    session: aiohttp.ClientSession,
    symbol: str = "BTCUSDT",
    interval: str = "15",
    limit: int = 250,
) -> list[list[str]]:
    """Получить свечи с рынка. Возвращаем сырые списки, как отдаёт Bybit.
    Порядок свечей Bybit: от новой к старой - мы разворачиваем его, чтобы
    старые свечи были в начале списка (удобно для индикаторов)."""
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    resp = await _request(session, "GET", "/v5/market/kline", params=params, auth=False)
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка get_klines: {resp.get('retMsg')}")
        return []
    raw = (resp.get("result") or {}).get("list") or []
    # Bybit возвращает от новых к старым - переворачиваем.
    return list(reversed(raw))


async def get_balance(
    session: aiohttp.ClientSession,
    coin: str = "USDT",
) -> Optional[float]:
    """Баланс по конкретной монете в Unified Trading Account."""
    params = {"accountType": "UNIFIED", "coin": coin}
    resp = await _request(
        session, "GET", "/v5/account/wallet-balance", params=params, auth=True
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка get_balance: {resp.get('retMsg')}")
        return None
    try:
        accounts = (resp.get("result") or {}).get("list") or []
        for acc in accounts:
            for c in acc.get("coin", []):
                if c.get("coin") == coin:
                    # walletBalance может приходить строкой.
                    wb = c.get("walletBalance") or c.get("equity") or "0"
                    return float(wb)
        return 0.0
    except (TypeError, ValueError, KeyError) as exc:
        print(f"[API] Не удалось распарсить баланс: {exc}")
        return None


async def get_positions(
    session: aiohttp.ClientSession,
    symbol: str = "BTCUSDT",
) -> list[dict[str, Any]]:
    """Открытые позиции по символу. Возвращаем только позиции с ненулевым size."""
    params = {"category": "linear", "symbol": symbol}
    resp = await _request(
        session, "GET", "/v5/position/list", params=params, auth=True
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка get_positions: {resp.get('retMsg')}")
        return []
    items = (resp.get("result") or {}).get("list") or []
    out: list[dict[str, Any]] = []
    for p in items:
        try:
            size = float(p.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size > 0:
            out.append(p)
    return out


# --- v2: инструментальные фильтры ---

_INSTRUMENT_CACHE: dict[str, dict[str, float]] = {}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


async def get_instruments_info(
    session: aiohttp.ClientSession,
    symbol: str,
) -> Optional[dict[str, float]]:
    """Получить биржевые фильтры по символу: minOrderQty, qtyStep,
    minNotionalValue, tickSize. Все значения - float. Публичный эндпоинт,
    аутентификация не нужна."""
    params = {"category": "linear", "symbol": symbol}
    resp = await _request(
        session, "GET", "/v5/market/instruments-info", params=params, auth=False
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка get_instruments_info: {resp.get('retMsg')}")
        return None
    items = (resp.get("result") or {}).get("list") or []
    if not items:
        print(f"[API] get_instruments_info: пустой список для {symbol}")
        return None
    item = items[0]
    lot = item.get("lotSizeFilter") or {}
    price = item.get("priceFilter") or {}
    info = {
        "minOrderQty": _safe_float(lot.get("minOrderQty"), 0.0),
        "qtyStep": _safe_float(lot.get("qtyStep"), 0.0),
        "minNotionalValue": _safe_float(lot.get("minNotionalValue"), 0.0),
        "tickSize": _safe_float(price.get("tickSize"), 0.0),
    }
    return info


async def instrument_info_cached(
    session: aiohttp.ClientSession,
    symbol: str,
) -> Optional[dict[str, float]]:
    """Кэшированная версия get_instruments_info: первый вызов ходит в сеть,
    последующие отдают значение из _INSTRUMENT_CACHE. На сетевом сбое
    возвращаем None и кэш не портим."""
    cached = _INSTRUMENT_CACHE.get(symbol)
    if cached is not None:
        return cached
    info = await get_instruments_info(session, symbol)
    if info is not None:
        _INSTRUMENT_CACHE[symbol] = info
    return info


def validate_and_round_qty(qty: float, info: dict[str, float], price: float) -> float:
    """Привести qty к биржевым фильтрам:
      - округлить вниз до qtyStep;
      - проверить qty >= minOrderQty;
      - проверить qty * price >= minNotionalValue.
    При провале любой проверки возвращаем 0.0 - это сигнал «не открывать»."""
    try:
        q = float(qty)
        p = float(price)
    except (TypeError, ValueError):
        return 0.0
    if q <= 0 or p <= 0 or not info:
        return 0.0

    step = _safe_float(info.get("qtyStep"), 0.0)
    min_qty = _safe_float(info.get("minOrderQty"), 0.0)
    min_notional = _safe_float(info.get("minNotionalValue"), 0.0)

    if step > 0:
        # floor(q / step) * step в числах с плавающей точкой.
        q = math.floor(q / step) * step
        # Округляем до разумной точности, чтобы не тащить 1e-17 хвосты.
        # Количество значащих цифр вычисляем через step.
        digits = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
        q = round(q, digits) if digits else float(int(q))

    if q <= 0:
        return 0.0
    if min_qty > 0 and q < min_qty:
        return 0.0
    if min_notional > 0 and (q * p) < min_notional:
        return 0.0
    return float(q)


async def get_orderbook_top(
    session: aiohttp.ClientSession,
    symbol: str,
) -> Optional[tuple[float, float]]:
    """Вершина стакана: (best_bid, best_ask). None при ошибке или пустом стакане."""
    params = {"category": "linear", "symbol": symbol, "limit": 1}
    resp = await _request(
        session, "GET", "/v5/market/orderbook", params=params, auth=False
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка get_orderbook_top: {resp.get('retMsg')}")
        return None
    result = resp.get("result") or {}
    bids = result.get("b") or []
    asks = result.get("a") or []
    if not bids or not asks:
        return None
    try:
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
    except (IndexError, TypeError, ValueError) as exc:
        print(f"[API] get_orderbook_top: битый стакан {exc}")
        return None
    return best_bid, best_ask


# --- v2: живые лимиты ---

async def get_open_orders(
    session: aiohttp.ClientSession,
    symbol: str,
) -> list[dict[str, Any]]:
    """Список активных (не исполненных) ордеров по символу."""
    params = {"category": "linear", "symbol": symbol}
    resp = await _request(
        session, "GET", "/v5/order/realtime", params=params, auth=True
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка get_open_orders: {resp.get('retMsg')}")
        return []
    return list((resp.get("result") or {}).get("list") or [])


async def cancel_order(
    session: aiohttp.ClientSession,
    symbol: str,
    order_id: str,
) -> Optional[dict[str, Any]]:
    """Отменить ордер по order_id."""
    body = {
        "category": "linear",
        "symbol": symbol,
        "orderId": str(order_id),
    }
    resp = await _request(session, "POST", "/v5/order/cancel", body=body, auth=True)
    if resp and resp.get("retCode") != 0:
        print(f"[API] Ошибка cancel_order: {resp.get('retMsg')}")
    return resp


# --- v2: ордерные функции ---

async def place_market_order(
    session: aiohttp.ClientSession,
    symbol: str,
    side: str,
    qty: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    reduce_only: bool = False,
) -> Optional[dict[str, Any]]:
    """Рыночный ордер IOC на Bybit V5 (category=linear). SL/TP прикрепляются
    сразу при наличии. side строго 'Buy' или 'Sell'."""
    body: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "IOC",
        "reduceOnly": bool(reduce_only),
    }
    if stop_loss is not None:
        body["stopLoss"] = str(stop_loss)
    if take_profit is not None:
        body["takeProfit"] = str(take_profit)
    resp = await _request(
        session, "POST", "/v5/order/create", body=body, auth=True
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка place_market_order: {resp.get('retMsg')}")
        return resp
    return resp


async def place_order(
    session: aiohttp.ClientSession,
    symbol: str,
    side: str,
    qty: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    reduce_only: bool = False,
) -> Optional[dict[str, Any]]:
    """Совместимость с v1: тонкий wrapper над place_market_order."""
    return await place_market_order(
        session,
        symbol=symbol,
        side=side,
        qty=qty,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reduce_only=reduce_only,
    )


async def place_post_only_limit(
    session: aiohttp.ClientSession,
    symbol: str,
    side: str,
    qty: float,
    limit_price: float,
    reduce_only: bool = False,
) -> Optional[dict[str, Any]]:
    """PostOnly-лимит: ордер, который НИКОГДА не matchит как taker.

    SL/TP на PostOnly-лимит Bybit в одном теле не приклеиваем: после filla
    позиции нужно отдельным вызовом set_trading_stop() повесить стопы.
    Это контракт v2: caller/place_order_with_fallback отвечают за SL/TP.
    """
    body: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Limit",
        "qty": str(qty),
        "price": str(limit_price),
        "timeInForce": "PostOnly",
        "reduceOnly": bool(reduce_only),
    }
    resp = await _request(
        session, "POST", "/v5/order/create", body=body, auth=True
    )
    if not resp or resp.get("retCode") != 0:
        if resp:
            print(f"[API] Ошибка place_post_only_limit: {resp.get('retMsg')}")
        return resp
    return resp


async def place_order_with_fallback(
    session: aiohttp.ClientSession,
    symbol: str,
    side: str,
    qty: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    reduce_only: bool = False,
) -> Optional[dict[str, Any]]:
    """Сначала PostOnly-лимит на одном tick от вершины стакана; если за
    POST_ONLY_TIMEOUT_SEC ордер не ушёл - отменяем и добиваем Market IOC
    с прикреплёнными SL/TP.

    Для Buy ставим на best_bid - tickSize, для Sell на best_ask + tickSize -
    гарантирует, что ордер сидит в стакане как maker и не станет taker.
    Если стакан/инструмент недоступны - сразу идём в market, логируя причину.
    """
    info = await instrument_info_cached(session, symbol)
    top = await get_orderbook_top(session, symbol)

    if info and top:
        tick = float(info.get("tickSize") or 0.0)
        best_bid, best_ask = top
        limit_price: Optional[float] = None
        if side == "Buy":
            limit_price = best_bid - tick if tick > 0 else best_bid
        elif side == "Sell":
            limit_price = best_ask + tick if tick > 0 else best_ask
        else:
            print(f"[API] place_order_with_fallback: неизвестный side={side}")
            return None

        # Приводим цену к сетке tickSize (округлением к ближайшему).
        if tick > 0 and limit_price is not None:
            limit_price = round(limit_price / tick) * tick

        limit_resp = await place_post_only_limit(
            session,
            symbol=symbol,
            side=side,
            qty=qty,
            limit_price=limit_price if limit_price is not None else 0.0,
            reduce_only=reduce_only,
        )
        order_id: Optional[str] = None
        if limit_resp and limit_resp.get("retCode") == 0:
            order_id = (limit_resp.get("result") or {}).get("orderId")
            print(
                f"[API] PostOnly-лимит размещён: {side} {qty} {symbol} "
                f"@ {limit_price} id={order_id}"
            )
        else:
            print("[API] PostOnly не прошёл, переходим к Market IOC")

        if order_id:
            # Ждём до POST_ONLY_TIMEOUT_SEC, периодически опрашивая стакан ордеров.
            deadline = time.time() + float(config.POST_ONLY_TIMEOUT_SEC)
            poll_interval = max(
                1.0,
                float(config.POST_ONLY_TIMEOUT_SEC) / 6.0,
            )
            filled = False
            while time.time() < deadline:
                await asyncio.sleep(poll_interval)
                open_orders = await get_open_orders(session, symbol)
                still_there = any(
                    (o or {}).get("orderId") == order_id for o in open_orders
                )
                if not still_there:
                    # Ордер больше не активен - считаем filled.
                    filled = True
                    break
            if filled:
                print(f"[API] PostOnly-лимит {order_id} исполнен в стакане")
                # SL/TP навесим отдельно через set_trading_stop.
                if stop_loss is not None or take_profit is not None:
                    await set_trading_stop(
                        session,
                        symbol=symbol,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                    )
                return limit_resp
            # Timeout: отменяем лимит и идём в market.
            print(
                f"[API] PostOnly-лимит {order_id} не исполнен за "
                f"{config.POST_ONLY_TIMEOUT_SEC}с, отменяем и падаем в Market"
            )
            await cancel_order(session, symbol, order_id)
    else:
        print(
            "[API] Нет данных инструмента или стакана - сразу Market IOC "
            f"(info={bool(info)}, top={bool(top)})"
        )

    return await place_market_order(
        session,
        symbol=symbol,
        side=side,
        qty=qty,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reduce_only=reduce_only,
    )


async def set_trading_stop(
    session: aiohttp.ClientSession,
    symbol: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Обновить SL/TP у уже открытой позиции (перевод в безубыток / трейлинг)."""
    body: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "positionIdx": 0,
    }
    if stop_loss is not None:
        body["stopLoss"] = str(stop_loss)
    if take_profit is not None:
        body["takeProfit"] = str(take_profit)
    resp = await _request(
        session, "POST", "/v5/position/trading-stop", body=body, auth=True
    )
    if resp and resp.get("retCode") != 0:
        print(f"[API] Ошибка set_trading_stop: {resp.get('retMsg')}")
    return resp


async def panic_sell(
    session: aiohttp.ClientSession,
    symbol: str = "BTCUSDT",
) -> list[dict[str, Any]]:
    """Аварийное закрытие всех открытых позиций по символу reduce-only маркетом."""
    positions = await get_positions(session, symbol)
    results: list[dict[str, Any]] = []
    for p in positions:
        try:
            size = float(p.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size <= 0:
            continue
        pos_side = (p.get("side") or "").strip()
        if pos_side not in ("Buy", "Sell"):
            continue
        close_side = "Sell" if pos_side == "Buy" else "Buy"
        print(f"[API] PANIC SELL: закрываем {pos_side} {size} {symbol}")
        resp = await place_order(
            session,
            symbol=symbol,
            side=close_side,
            qty=size,
            reduce_only=True,
        )
        if resp:
            results.append(resp)
    if not results:
        print(f"[API] PANIC SELL: открытых позиций по {symbol} не найдено")
    return results
