"""Адаптер OKX V5 (линейные перпетуалы SWAP).

Особенности OKX против Bybit:
  - Подпись: Base64(HMAC_SHA256(secret, timestamp + method + path + body)).
  - Timestamp в заголовке: ISO 8601 с миллисекундами (2024-01-02T03:04:05.678Z).
  - Демо-счёт: обязательный заголовок x-simulated-trading: 1 на ВСЕХ запросах
    (и публичных, и приватных), когда config.IS_TESTNET=True.
  - Символ SWAP: BTC-USDT-SWAP (дефисы, суффикс -SWAP).
  - Таймфреймы: 1m/15m/1H/4H/1D (буквенные). Биржевые интервалы Bybit
    (1/15/60/240/D) транслируются через _INTERVAL_MAP.
  - Stop Loss / Take Profit - отдельный algo-ордер через /trade/order-algo.
  - Ответ сервера завёрнут в {code:"0", msg, data:[...]}. code="0" = успех.

В ответах адаптер НОРМАЛИЗУЕТ формат под тот, что ожидает существующий код
(совместимо с api_engine/bybit): для get_klines возвращается list[list[str]]
в порядке от старых свечей к новым, для get_positions, place_order и
прочих - dict с ключами retCode/retMsg/result/fill_price/fill_qty.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp

import config
from .base import ExchangeAdapter


_OKX_BASE_URL = "https://www.okx.com"

# Маппинг bybit-интервалов в OKX.
_INTERVAL_MAP = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1H",
    "120": "2H",
    "240": "4H",
    "360": "6H",
    "720": "12H",
    "D": "1D",
    "W": "1W",
    "M": "1M",
}


def _normalize_symbol(symbol: str) -> str:
    """BTCUSDT -> BTC-USDT-SWAP. Уже нормализованный символ возвращается как есть."""
    s = (symbol or "").strip().upper()
    if not s:
        return s
    if "-" in s:
        # Уже BTC-USDT или BTC-USDT-SWAP.
        return s if s.endswith("-SWAP") else f"{s}-SWAP"
    if s.endswith("USDT"):
        return f"{s[:-4]}-USDT-SWAP"
    if s.endswith("USD"):
        return f"{s[:-3]}-USD-SWAP"
    return s


def _normalize_interval(interval: str) -> str:
    s = str(interval or "").strip()
    return _INTERVAL_MAP.get(s, s)


def _okx_ts() -> str:
    """ISO-8601 в UTC с миллисекундами, суффикс Z (требование OKX V5)."""
    now = datetime.now(tz=timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _map_ret_code(resp: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Нормализовать OKX-ответ под Bybit-подобный шейп с retCode/retMsg.
    Мутирует и возвращает тот же словарь для удобства chain-записи."""
    if not isinstance(resp, dict):
        return {"retCode": -1, "retMsg": "empty response", "result": {}}
    code = resp.get("code")
    try:
        resp["retCode"] = 0 if str(code) == "0" else (int(code) if code not in (None, "") else -1)
    except (TypeError, ValueError):
        resp["retCode"] = -1
    resp["retMsg"] = resp.get("msg") or ""
    # result обычно первая запись data[] (если есть).
    data = resp.get("data") or []
    resp["result"] = data[0] if data else {}
    return resp


class OKXAdapter(ExchangeAdapter):
    """Адаптер OKX V5 для линейных SWAP-перпетуалов."""

    name = "okx"

    def __init__(self, **_: Any) -> None:
        self.api_key = os.getenv("OKX_API_KEY", "")
        self.api_secret = os.getenv("OKX_API_SECRET", "")
        self.passphrase = os.getenv("OKX_PASSPHRASE", "")
        # IS_TESTNET в config означает "демо-счёт OKX".
        self.is_testnet = bool(getattr(config, "IS_TESTNET", True))
        self.base_url = _OKX_BASE_URL
        self._instrument_cache: dict[str, dict[str, float]] = {}

    # --- Подпись и HTTP-обёртка -------------------------------------------

    def _sign(self, ts: str, method: str, path_with_query: str, body: str) -> str:
        prehash = ts + method.upper() + path_with_query + (body or "")
        digest = hmac.new(
            self.api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _auth_headers(self, method: str, path_with_query: str, body: str) -> dict[str, str]:
        ts = _okx_ts()
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": self._sign(ts, method, path_with_query, body),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if self.is_testnet:
            headers["x-simulated-trading"] = "1"
        return headers

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
        auth: bool = False,
        timeout: int = 15,
    ) -> Optional[dict[str, Any]]:
        params = params or {}
        body = body or {}
        try:
            if method.upper() == "GET":
                query = urlencode(params) if params else ""
                path_with_query = path + (f"?{query}" if query else "")
                full_url = self.base_url + path_with_query
                if auth:
                    headers = self._auth_headers("GET", path_with_query, "")
                else:
                    headers = {}
                    if self.is_testnet:
                        headers["x-simulated-trading"] = "1"
                async with session.get(full_url, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
            elif method.upper() == "POST":
                body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
                full_url = self.base_url + path
                if auth:
                    headers = self._auth_headers("POST", path, body_str)
                else:
                    headers = {"Content-Type": "application/json"}
                    if self.is_testnet:
                        headers["x-simulated-trading"] = "1"
                async with session.post(
                    full_url, data=body_str, headers=headers, timeout=timeout
                ) as resp:
                    text = await resp.text()
            else:
                print(f"[OKX] Неподдерживаемый метод: {method}")
                return None

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                print(f"[OKX] Невалидный JSON от {path}: {text[:200]}")
                return None
        except aiohttp.ClientError as exc:
            print(f"[OKX] Сетевая ошибка {path}: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[OKX] Неожиданная ошибка {path}: {exc}")
            return None

    # --- Публичные эндпоинты ---------------------------------------------

    async def get_server_time(self, session: Any) -> Optional[int]:
        resp = await self._request(session, "GET", "/api/v5/public/time", auth=False)
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_server_time: {resp.get('msg')}")
            return None
        data = resp.get("data") or []
        if not data:
            return None
        try:
            return int(data[0].get("ts") or 0)
        except (TypeError, ValueError):
            return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[list[str]]:
        """Возвращаем list[list[str]] в порядке от старых свечей к новым.
        Совместимо с api_engine/bybit формат: [ts, open, high, low, close, volume, ...]."""
        norm = _normalize_symbol(symbol)
        bar = _normalize_interval(interval)
        safe_limit = max(1, min(300, int(limit)))
        params = {"instId": norm, "bar": bar, "limit": safe_limit}
        resp = await self._request(
            session, "GET", "/api/v5/market/candles", params=params, auth=False
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_klines: {resp.get('msg')}")
            return []
        data = resp.get("data") or []
        # OKX отдаёт новые первыми - переворачиваем.
        out: list[list[str]] = []
        for row in reversed(data):
            try:
                # [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
                out.append([
                    str(row[0]),
                    str(row[1]),
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    str(row[5]) if len(row) > 5 else "0",
                ])
            except (IndexError, TypeError):
                continue
        return out

    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        norm = _normalize_symbol(symbol)
        params = {"instType": "SWAP", "instId": norm}
        resp = await self._request(
            session, "GET", "/api/v5/public/instruments", params=params, auth=False
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_instrument_info: {resp.get('msg')}")
            return None
        data = resp.get("data") or []
        if not data:
            return None
        item = data[0]
        return {
            "minOrderQty": _safe_float(item.get("minSz")),
            "qtyStep": _safe_float(item.get("lotSz")),
            "minNotionalValue": 0.0,  # OKX не отдаёт этот фильтр напрямую.
            "tickSize": _safe_float(item.get("tickSz")),
        }

    async def instrument_info_cached(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        norm = _normalize_symbol(symbol)
        cached = self._instrument_cache.get(norm)
        if cached is not None:
            return cached
        info = await self.get_instrument_info(session, norm)
        if info is not None:
            self._instrument_cache[norm] = info
        return info

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        norm = _normalize_symbol(symbol)
        params = {"instId": norm, "sz": 1}
        resp = await self._request(
            session, "GET", "/api/v5/market/books", params=params, auth=False
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_orderbook_top: {resp.get('msg')}")
            return None
        data = resp.get("data") or []
        if not data:
            return None
        book = data[0]
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            return None
        try:
            return float(bids[0][0]), float(asks[0][0])
        except (IndexError, TypeError, ValueError) as exc:
            print(f"[OKX] get_orderbook_top: битый стакан {exc}")
            return None

    # --- Приватные эндпоинты ---------------------------------------------

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        params = {"ccy": coin}
        resp = await self._request(
            session, "GET", "/api/v5/account/balance", params=params, auth=True
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_balance: {resp.get('msg')}")
            return None
        data = resp.get("data") or []
        if not data:
            return 0.0
        details = data[0].get("details") or []
        for item in details:
            if str(item.get("ccy") or "").upper() == coin.upper():
                # availBal - доступный баланс; eq - эквити (equity).
                avail = item.get("availBal") or item.get("cashBal") or item.get("eq") or "0"
                return _safe_float(avail)
        return 0.0

    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        norm = _normalize_symbol(symbol)
        params = {"instType": "SWAP", "instId": norm}
        resp = await self._request(
            session, "GET", "/api/v5/account/positions", params=params, auth=True
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_positions: {resp.get('msg')}")
            return []
        data = resp.get("data") or []
        out: list[dict[str, Any]] = []
        for item in data:
            pos = _safe_float(item.get("pos"))
            if pos == 0:
                continue
            out.append({
                "symbol": item.get("instId"),
                "side": "Buy" if pos > 0 else "Sell",
                "size": abs(pos),
                "avgPrice": _safe_float(item.get("avgPx")),
                "unrealisedPnl": _safe_float(item.get("upl")),
                "raw": item,
            })
        return out

    async def get_closed_pnl(
        self, session: Any, symbol: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        norm = _normalize_symbol(symbol)
        params = {"instType": "SWAP", "instId": norm, "limit": max(1, min(100, int(limit)))}
        resp = await self._request(
            session, "GET", "/api/v5/account/positions-history", params=params, auth=True
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_closed_pnl: {resp.get('msg')}")
            return []
        data = resp.get("data") or []
        out: list[dict[str, Any]] = []
        for item in data:
            out.append({
                "symbol": item.get("instId"),
                "closedPnl": _safe_float(item.get("realizedPnl") or item.get("pnl")),
                "avgExitPrice": _safe_float(item.get("closeAvgPx")),
                "closedSize": _safe_float(item.get("closeTotalPos")),
                "createdTime": item.get("cTime"),
                "raw": item,
            })
        return out

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        norm = _normalize_symbol(symbol)
        params = {
            "instType": "SWAP",
            "instId": norm,
            "ordId": order_id,
            "limit": max(1, min(100, int(limit))),
        }
        resp = await self._request(
            session, "GET", "/api/v5/trade/fills", params=params, auth=True
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_execution_history: {resp.get('msg')}")
            return []
        data = resp.get("data") or []
        out: list[dict[str, Any]] = []
        for item in data:
            out.append({
                "execQty": _safe_float(item.get("fillSz")),
                "execPrice": _safe_float(item.get("fillPx")),
                "orderId": item.get("ordId"),
                "ts": item.get("ts"),
                "raw": item,
            })
        return out

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        norm = _normalize_symbol(symbol)
        params = {"instType": "SWAP", "instId": norm}
        resp = await self._request(
            session, "GET", "/api/v5/trade/orders-pending", params=params, auth=True
        )
        if not resp or str(resp.get("code")) != "0":
            if resp:
                print(f"[OKX] Ошибка get_open_orders: {resp.get('msg')}")
            return []
        data = resp.get("data") or []
        out: list[dict[str, Any]] = []
        for item in data:
            out.append({
                "orderId": item.get("ordId"),
                "price": _safe_float(item.get("px")),
                "side": item.get("side"),
                "sz": _safe_float(item.get("sz")),
                "raw": item,
            })
        return out

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        norm = _normalize_symbol(symbol)
        body = {"instId": norm, "ordId": order_id}
        resp = await self._request(
            session, "POST", "/api/v5/trade/cancel-order", body=body, auth=True
        )
        return _map_ret_code(resp)

    # --- Установка SL/TP через algo-ордер --------------------------------

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """В OKX SL/TP - это algo-ордер (ordType=conditional), а не атрибут
        позиции. Для определения стороны закрытия берём get_positions."""
        if stop_loss is None and take_profit is None:
            return {"retCode": -1, "retMsg": "no sl/tp provided", "result": {}}

        norm = _normalize_symbol(symbol)
        positions = await self.get_positions(session, norm)
        if not positions:
            print(f"[OKX] set_trading_stop: нет открытой позиции по {norm}")
            return {"retCode": -1, "retMsg": "no open position", "result": {}}

        pos_side = str(positions[0].get("side") or "")
        close_side = "sell" if pos_side == "Buy" else "buy"

        body: dict[str, Any] = {
            "instId": norm,
            "tdMode": "cross",
            "side": close_side,
            "ordType": "conditional",
            "closeFraction": "1",
            "reduceOnly": "true",
        }
        if stop_loss is not None:
            body["slTriggerPx"] = str(stop_loss)
            body["slOrdPx"] = "-1"  # закрыть по маркету при срабатывании
        if take_profit is not None:
            body["tpTriggerPx"] = str(take_profit)
            body["tpOrdPx"] = "-1"

        resp = await self._request(
            session, "POST", "/api/v5/trade/order-algo", body=body, auth=True
        )
        return _map_ret_code(resp)

    # --- Размещение ордеров ----------------------------------------------

    async def _place_raw_order(
        self,
        session: aiohttp.ClientSession,
        norm_symbol: str,
        side: str,
        ord_type: str,
        qty: float,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Optional[dict[str, Any]]:
        body: dict[str, Any] = {
            "instId": norm_symbol,
            "tdMode": "cross",
            "side": side.lower(),
            "ordType": ord_type,
            "sz": str(qty),
        }
        if price is not None:
            body["px"] = str(price)
        if reduce_only:
            body["reduceOnly"] = "true"
        resp = await self._request(
            session, "POST", "/api/v5/trade/order", body=body, auth=True
        )
        return resp

    def _weighted_avg_fill(self, fills: list[dict[str, Any]]) -> tuple[float, float]:
        total_q = 0.0
        total_c = 0.0
        for f in fills:
            q = _safe_float(f.get("execQty"))
            p = _safe_float(f.get("execPrice"))
            total_q += q
            total_c += q * p
        if total_q <= 0:
            return 0.0, 0.0
        return total_c / total_q, total_q

    async def place_order_with_fallback(
        self,
        session: Any,
        symbol: str,
        side: str,
        qty: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
        post_only_timeout_sec: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """PostOnly Limit -> IOC Market fallback. Возвращает dict в bybit-подобном
        формате: {retCode, retMsg, result:{orderId}, fill_price, fill_qty}."""
        norm = _normalize_symbol(symbol)
        timeout = int(post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 30))

        # 1. Попытка PostOnly.
        book_top = await self.get_orderbook_top(session, norm)
        po_ord_id: Optional[str] = None
        if book_top:
            best_bid, best_ask = book_top
            limit_price = best_bid if side.lower() == "buy" else best_ask
            po_resp = await self._place_raw_order(
                session, norm, side, "post_only", qty, price=limit_price,
                reduce_only=reduce_only,
            )
            if po_resp and str(po_resp.get("code")) == "0":
                po_data = po_resp.get("data") or []
                if po_data:
                    po_ord_id = po_data[0].get("ordId")
            else:
                if po_resp:
                    print(f"[OKX] PostOnly отклонён: {po_resp.get('msg')}")

        # 2. Ожидание fill или таймаут.
        if po_ord_id:
            deadline = time.time() + max(1, timeout)
            filled = False
            while time.time() < deadline:
                await asyncio.sleep(2)
                orders = await self.get_open_orders(session, norm)
                still_there = any(
                    str((o or {}).get("orderId")) == str(po_ord_id) for o in orders
                )
                if not still_there:
                    filled = True
                    break

            if filled:
                # PostOnly отсутствует в open_orders по трём причинам:
                # filled, cancelled, rejected. Подтверждаем через executions.
                fills = await self.get_execution_history(session, norm, po_ord_id, 5)
                if fills:
                    avg_px, total_q = self._weighted_avg_fill(fills)
                    result = {
                        "retCode": 0,
                        "retMsg": "OK (PostOnly)",
                        "result": {"orderId": po_ord_id},
                        "fill_price": avg_px,
                        "fill_qty": total_q,
                    }
                    if stop_loss is not None or take_profit is not None:
                        try:
                            await self.set_trading_stop(
                                session, norm, stop_loss=stop_loss, take_profit=take_profit
                            )
                        except Exception as exc:  # noqa: BLE001
                            print(f"[OKX] Не удалось установить SL/TP: {exc}")
                    return result
                else:
                    print(f"[OKX] PostOnly {po_ord_id} исчез без исполнений - отмена")
                    await self.cancel_order(session, norm, po_ord_id)
            else:
                # Не заполнился за таймаут - отменяем и идём в market.
                print(f"[OKX] PostOnly {po_ord_id} не заполнился за {timeout}с - отмена")
                await self.cancel_order(session, norm, po_ord_id)

        # 3. Market IOC fallback.
        mk_resp = await self._place_raw_order(
            session, norm, side, "market", qty, reduce_only=reduce_only,
        )
        if not mk_resp or str(mk_resp.get("code")) != "0":
            return {
                "retCode": -1,
                "retMsg": (mk_resp.get("msg") if mk_resp else "network error"),
                "result": {},
            }
        mk_data = mk_resp.get("data") or []
        if not mk_data:
            return {"retCode": -1, "retMsg": "no data in response", "result": {}}
        mk_ord_id = mk_data[0].get("ordId")
        if not mk_ord_id:
            return {"retCode": -1, "retMsg": "no ordId in response", "result": {}}

        await asyncio.sleep(1)
        mk_fills = await self.get_execution_history(session, norm, mk_ord_id, 5)
        avg_px, total_q = self._weighted_avg_fill(mk_fills)
        result = {
            "retCode": 0,
            "retMsg": "OK (Market)",
            "result": {"orderId": mk_ord_id},
            "fill_price": avg_px,
            "fill_qty": total_q,
        }
        if stop_loss is not None or take_profit is not None:
            try:
                await self.set_trading_stop(
                    session, norm, stop_loss=stop_loss, take_profit=take_profit
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[OKX] Не удалось установить SL/TP после market fallback: {exc}")
        return result

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        """Аварийное закрытие всех позиций по символу reduce-only маркетом."""
        norm = _normalize_symbol(symbol)
        positions = await self.get_positions(session, norm)
        results: list[dict[str, Any]] = []
        for p in positions:
            size = _safe_float(p.get("size"))
            if size <= 0:
                continue
            pos_side = str(p.get("side") or "")
            close_side = "Sell" if pos_side == "Buy" else "Buy"
            print(f"[OKX] PANIC SELL: закрываем {pos_side} {size} {norm}")
            resp = await self.place_order_with_fallback(
                session, norm, side=close_side, qty=size, reduce_only=True,
            )
            if resp:
                results.append(resp)
        if not results:
            print(f"[OKX] PANIC SELL: открытых позиций по {norm} не найдено")
        return results

    # --- Фильтры инструмента --------------------------------------------

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        """Привести qty к биржевым фильтрам:
          - округлить вниз до qtyStep;
          - проверить qty >= minOrderQty;
          - проверить qty * price >= minNotionalValue (если задан).
        При провале любой проверки возвращаем 0.0 - это сигнал «не открывать»."""
        try:
            q = float(qty)
            p = float(price)
        except (TypeError, ValueError):
            return 0.0
        if q <= 0 or p <= 0 or not info:
            return 0.0

        step = _safe_float(info.get("qtyStep"))
        min_qty = _safe_float(info.get("minOrderQty"))
        min_notional = _safe_float(info.get("minNotionalValue"))

        if step > 0:
            q = math.floor(q / step) * step
            digits = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
            q = round(q, digits) if digits else float(int(q))

        if q <= 0:
            return 0.0
        if min_qty > 0 and q < min_qty:
            return 0.0
        if min_notional > 0 and (q * p) < min_notional:
            return 0.0
        return float(q)
