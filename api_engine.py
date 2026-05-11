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
"""

from __future__ import annotations

import hashlib
import hmac
import json
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


async def place_order(
    session: aiohttp.ClientSession,
    symbol: str,
    side: str,
    qty: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    reduce_only: bool = False,
) -> Optional[dict[str, Any]]:
    """Рыночный ордер на Bybit V5 (category=linear). SL/TP прикрепляются сразу.
    side должен быть 'Buy' или 'Sell'."""
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
            print(f"[API] Ошибка place_order: {resp.get('retMsg')}")
        return resp
    return resp


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
