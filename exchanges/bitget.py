"""Адаптер Bitget USDT-M Futures (Mix API v2).

Документация: https://www.bitget.com/api-doc/contract/market/
Auth: HMAC-SHA256 → base64.
  timestamp(ms) + METHOD.upper() + requestPath + (queryString|body)
Заголовки: ACCESS-KEY, ACCESS-SIGN, ACCESS-TIMESTAMP, ACCESS-PASSPHRASE,
           Content-Type: application/json.
Mainnet: https://api.bitget.com
Testnet: https://testnet.bitgetapi.com (только часть эндпоинтов).
ProductType: USDT-FUTURES.
Символ: BTCUSDT (без разделителя, как у нас).
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
import uuid
from typing import Any, Optional
from urllib.parse import urlencode

import config
from .base import ExchangeAdapter

_BASE_MAINNET = "https://api.bitget.com"
_BASE_TESTNET = "https://testnet.bitgetapi.com"
_PRODUCT = "USDT-FUTURES"

_INSTRUMENT_CACHE: dict[str, dict[str, float]] = {}


def _round_qty(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    precision = max(0, round(-math.log10(step)))
    return round(math.floor(qty / step) * step, precision)


class BitgetAdapter(ExchangeAdapter):
    """Bitget USDT-M Futures адаптер."""

    name = "bitget"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET
        self._base = _BASE_TESTNET if self.is_testnet else _BASE_MAINNET

    def _key(self) -> str:
        return os.getenv("BITGET_API_KEY", "")

    def _secret(self) -> str:
        return os.getenv("BITGET_API_SECRET", "")

    def _passphrase(self) -> str:
        return os.getenv("BITGET_PASSPHRASE", "")

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        pre = timestamp + method.upper() + path + body
        raw = hmac.new(
            self._secret().encode(), pre.encode(), hashlib.sha256
        ).digest()
        return base64.b64encode(raw).decode()

    def _auth_headers(
        self, method: str, path: str, body: str = ""
    ) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        return {
            "ACCESS-KEY": self._key(),
            "ACCESS-SIGN": self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self._passphrase(),
            "Content-Type": "application/json",
        }

    async def _get(
        self,
        session: Any,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Optional[Any]:
        qs = ("?" + urlencode(params)) if params else ""
        headers = self._auth_headers("GET", path + qs) if signed else {}
        try:
            async with session.get(
                self._base + path, params=params, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BITGET] GET {path}: {exc}")
            return None

    async def _post(
        self, session: Any, path: str, body: dict[str, Any]
    ) -> Optional[Any]:
        raw = json.dumps(body)
        headers = self._auth_headers("POST", path, raw)
        try:
            async with session.post(
                self._base + path, data=raw, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BITGET] POST {path}: {exc}")
            return None

    async def _delete(
        self, session: Any, path: str, body: dict[str, Any]
    ) -> Optional[Any]:
        raw = json.dumps(body)
        headers = self._auth_headers("DELETE", path, raw)
        try:
            async with session.delete(
                self._base + path, data=raw, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BITGET] DELETE {path}: {exc}")
            return None

    async def get_server_time(self, session: Any) -> Optional[int]:
        resp = await self._get(session, "/api/v2/public/time")
        if isinstance(resp, dict) and resp.get("code") == "00000":
            try:
                return int((resp.get("data") or {}).get("serverTime", 0))
            except (TypeError, ValueError):
                return None
        return None

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        resp = await self._get(
            session,
            "/api/v2/mix/account/accounts",
            {"productType": _PRODUCT},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return None
        for item in resp.get("data") or []:
            if (item.get("marginCoin") or "").upper() == coin.upper():
                try:
                    return float(item.get("available") or 0)
                except (TypeError, ValueError):
                    return None
        return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        _MAP = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1H", "240": "4H", "D": "1Dutc"}
        bg_interval = _MAP.get(interval, "1H")
        resp = await self._get(session, "/api/v2/mix/market/candles", {
            "symbol": symbol, "productType": _PRODUCT,
            "granularity": bg_interval, "limit": str(limit),
        })
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return []
        result: list[dict[str, Any]] = []
        for k in resp.get("data") or []:
            try:
                result.append({
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            except (IndexError, TypeError, ValueError):
                continue
        return result

    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        if symbol in _INSTRUMENT_CACHE:
            return _INSTRUMENT_CACHE[symbol]
        resp = await self._get(session, "/api/v2/mix/market/contracts", {
            "productType": _PRODUCT, "symbol": symbol,
        })
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return None
        for s in resp.get("data") or []:
            if s.get("symbol") != symbol:
                continue
            try:
                info: dict[str, float] = {
                    "min_qty": float(s.get("minTradeNum") or 0),
                    "qty_step": float(s.get("sizeMultiplier") or s.get("minTradeNum") or 0),
                    "min_notional": 0.0,
                    "tick_size": float(s.get("pricePlace") and
                                       10 ** (-int(s["pricePlace"])) or 0.01),
                    "contract_size": float(s.get("sizeMultiplier") or 1.0),
                }
                _INSTRUMENT_CACHE[symbol] = info
                return info
            except (TypeError, ValueError):
                pass
        return None

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        resp = await self._get(session, "/api/v2/mix/market/depth", {
            "symbol": symbol, "productType": _PRODUCT, "limit": "5",
        })
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return None
        d = resp.get("data") or {}
        try:
            bid = float(d["bids"][0][0])
            ask = float(d["asks"][0][0])
            return bid, ask
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/api/v2/mix/position/single-position",
            {"productType": _PRODUCT, "symbol": symbol},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return []
        result: list[dict[str, Any]] = []
        for p in resp.get("data") or []:
            try:
                total = float(p.get("total") or 0)
                if total == 0:
                    continue
                hold_side = str(p.get("holdSide") or "long")
                result.append({
                    "symbol": symbol,
                    "side": "Buy" if hold_side == "long" else "Sell",
                    "size": total,
                    "avgPrice": float(p.get("openPriceAvg") or 0),
                    "unrealisedPnl": float(p.get("unrealizedPL") or 0),
                    "markPrice": float(p.get("markPrice") or 0),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_closed_pnl(
        self, session: Any, symbol: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/api/v2/mix/order/fill-history",
            {"productType": _PRODUCT, "symbol": symbol, "pageSize": str(limit)},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return []
        result: list[dict[str, Any]] = []
        for t in (resp.get("data") or {}).get("fillList") or []:
            try:
                result.append({
                    "symbol": symbol,
                    "orderId": str(t.get("orderId")),
                    "realizedPnl": float(t.get("profit") or 0),
                    "qty": float(t.get("baseVolume") or 0),
                    "price": float(t.get("price") or 0),
                    "ts": t.get("cTime"),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/api/v2/mix/order/fills",
            {"productType": _PRODUCT, "symbol": symbol, "orderId": order_id},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return []
        return resp.get("data") or []

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/api/v2/mix/order/orders-pending",
            {"productType": _PRODUCT, "symbol": symbol},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return []
        return (resp.get("data") or {}).get("entrustedList") or []

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._post(session, "/api/v2/mix/order/cancel-order", {
            "productType": _PRODUCT,
            "symbol": symbol,
            "orderId": order_id,
        })
        if isinstance(resp, dict) and resp.get("code") == "00000":
            return resp.get("data")
        return None

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        step = float(info.get("qty_step") or info.get("min_qty") or 0)
        min_qty = float(info.get("min_qty") or 0)
        rounded = _round_qty(qty, step) if step > 0 else qty
        if min_qty > 0 and rounded < min_qty:
            return 0.0
        return rounded

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        body: dict[str, Any] = {
            "productType": _PRODUCT,
            "symbol": symbol,
        }
        if stop_loss:
            body["stopLossPrice"] = str(stop_loss)
        if take_profit:
            body["takeProfitPrice"] = str(take_profit)
        return await self._post(session, "/api/v2/mix/order/place-tpsl-order", body)

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
        bg_side = "buy" if side == "Buy" else "sell"
        trade_side = "close" if reduce_only else "open"
        timeout = post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 30)
        client_oid = uuid.uuid4().hex[:16]

        ob = await self.get_orderbook_top(session, symbol)
        if not ob:
            return None
        bid, ask = ob
        limit_price = str(ask if bg_side == "buy" else bid)

        body: dict[str, Any] = {
            "symbol": symbol,
            "productType": _PRODUCT,
            "marginMode": "crossed",
            "marginCoin": "USDT",
            "size": str(qty),
            "price": limit_price,
            "side": bg_side,
            "tradeSide": trade_side,
            "orderType": "limit",
            "force": "post_only",
            "clientOid": client_oid,
        }
        resp = await self._post(session, "/api/v2/mix/order/place-order", body)
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            print(f"[BITGET] place_order post_only fail: {resp}")
            order_id = None
        else:
            order_id = str((resp.get("data") or {}).get("orderId") or "")

        if order_id:
            await asyncio.sleep(timeout)
            orders = await self.get_open_orders(session, symbol)
            still_open = any(str(o.get("orderId")) == order_id for o in orders)
            if not still_open:
                fills = await self.get_execution_history(session, symbol, order_id)
                if fills:
                    try:
                        fill_price = float((fills[0] or {}).get("price") or limit_price)
                    except (TypeError, ValueError):
                        fill_price = float(limit_price)
                    return {"order_id": order_id, "fill_price": fill_price, "fill_qty": qty}
            await self.cancel_order(session, symbol, order_id)

        body_mkt = {
            "symbol": symbol,
            "productType": _PRODUCT,
            "marginMode": "crossed",
            "marginCoin": "USDT",
            "size": str(qty),
            "side": bg_side,
            "tradeSide": trade_side,
            "orderType": "market",
            "force": "ioc",
            "clientOid": uuid.uuid4().hex[:16],
        }
        resp2 = await self._post(session, "/api/v2/mix/order/place-order", body_mkt)
        if not isinstance(resp2, dict) or resp2.get("code") != "00000":
            print(f"[BITGET] place_order market fail: {resp2}")
            return None
        mkt_id = str((resp2.get("data") or {}).get("orderId") or "")
        ob2 = await self.get_orderbook_top(session, symbol)
        fill_price = (ask if bg_side == "buy" else bid)
        if ob2:
            fill_price = ob2[1] if bg_side == "buy" else ob2[0]
        return {"order_id": mkt_id, "fill_price": fill_price, "fill_qty": qty}

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        positions = await self.get_positions(session, symbol)
        results = []
        for pos in positions:
            close_side = "sell" if pos["side"] == "Buy" else "buy"
            body = {
                "symbol": symbol,
                "productType": _PRODUCT,
                "marginMode": "crossed",
                "marginCoin": "USDT",
                "size": str(pos["size"]),
                "side": close_side,
                "tradeSide": "close",
                "orderType": "market",
                "force": "ioc",
                "clientOid": uuid.uuid4().hex[:16],
            }
            resp = await self._post(session, "/api/v2/mix/order/place-order", body)
            results.append(resp or {})
        return results

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._get(session, "/api/v2/mix/market/ticker", {
            "symbol": symbol, "productType": _PRODUCT,
        })
        if not isinstance(resp, dict) or resp.get("code") != "00000":
            return None
        data_list = resp.get("data") or []
        if not data_list:
            return None
        d = data_list[0]
        try:
            funding_rate = float(d.get("fundingRate") or 0)
            next_ts_raw = d.get("nextFundingTime") or 0
            next_ts = int(next_ts_raw) if next_ts_raw else 0
            mark_price = float(
                d.get("markPrice") or d.get("lastPr") or d.get("close") or 0
            )
            return {
                "symbol": symbol,
                "funding_rate": funding_rate,
                "next_funding_ts": next_ts,
                "mark_price": mark_price,
                "interval_hours": 8.0,
            }
        except (TypeError, ValueError):
            return None
