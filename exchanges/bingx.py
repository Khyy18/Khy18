"""Адаптер BingX Perpetual Swap (Standard Futures).

Документация: https://bingx-api.github.io/docs/#/en-us/swapV2/
Auth: HMAC-SHA256.
  Все параметры сортируются, к строке добавляется timestamp, результат подписывается.
  Заголовки: X-BX-APIKEY.
  Подпись передаётся в параметре signature.
Base: https://open-api.bingx.com
Символ: BTCUSDT → BTC-USDT (внутренний формат BingX).

Примечание: BingX работает в one-way mode (positionSide=BOTH) — упрощает
работу с арб-стратегией. Reduce-only через параметр reduceOnly=true.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlencode

import config
from .base import ExchangeAdapter

_BASE = "https://open-api.bingx.com"


def _sym(symbol: str) -> str:
    """BTCUSDT → BTC-USDT."""
    if symbol.endswith("USDT") and "-" not in symbol:
        return symbol[:-4] + "-USDT"
    return symbol


class BingXAdapter(ExchangeAdapter):
    """BingX USDT-M perpetual swap адаптер."""

    name = "bingx"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET

    def _key(self) -> str:
        return os.getenv("BINGX_API_KEY", "")

    def _secret(self) -> str:
        return os.getenv("BINGX_API_SECRET", "")

    def _sign(self, params: dict[str, Any]) -> str:
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(self._secret().encode(), qs.encode(), hashlib.sha256).hexdigest()

    def _auth_params(self, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        p: dict[str, Any] = dict(params or {})
        p["timestamp"] = str(int(time.time() * 1000))
        p["signature"] = self._sign(p)
        return p

    def _headers(self) -> dict[str, str]:
        return {"X-BX-APIKEY": self._key()}

    async def _get(
        self,
        session: Any,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Optional[Any]:
        p = self._auth_params(params) if signed else (params or {})
        try:
            async with session.get(
                _BASE + path, params=p, headers=self._headers() if signed else {}
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BINGX] GET {path}: {exc}")
            return None

    async def _post(
        self, session: Any, path: str, body: dict[str, Any]
    ) -> Optional[Any]:
        p = self._auth_params(body)
        try:
            async with session.post(
                _BASE + path, params=p, headers=self._headers()
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BINGX] POST {path}: {exc}")
            return None

    async def _delete(
        self, session: Any, path: str, params: dict[str, Any]
    ) -> Optional[Any]:
        p = self._auth_params(params)
        try:
            async with session.delete(
                _BASE + path, params=p, headers=self._headers()
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BINGX] DELETE {path}: {exc}")
            return None

    async def get_server_time(self, session: Any) -> Optional[int]:
        return int(time.time() * 1000)

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        resp = await self._get(session, "/openApi/swap/v2/user/balance", signed=True)
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return None
        b = (resp.get("data") or {}).get("balance") or {}
        try:
            return float(b.get("availableMargin") or b.get("equity") or 0)
        except (TypeError, ValueError):
            return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        _MAP = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1h", "240": "4h", "D": "1d"}
        bx_interval = _MAP.get(interval, "1h")
        resp = await self._get(session, "/openApi/swap/v2/quote/klines", {
            "symbol": _sym(symbol), "interval": bx_interval, "limit": str(limit),
        })
        if not isinstance(resp, dict) or resp.get("code") != 0:
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
        resp = await self._get(session, "/openApi/swap/v2/quote/contracts")
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return None
        bx_sym = _sym(symbol)
        for s in resp.get("data") or []:
            if s.get("symbol") != bx_sym:
                continue
            try:
                return {
                    "min_qty": float(s.get("tradeMinQuantity") or 0),
                    "qty_step": float(s.get("tradeMinQuantity") or 0),
                    "min_notional": float(s.get("tradeMinUSDT") or 0),
                    "tick_size": float(s.get("pricePrecision") and
                                       10 ** (-int(s["pricePrecision"])) or 0.01),
                    "contract_size": 1.0,
                }
            except (TypeError, ValueError):
                pass
        return None

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        resp = await self._get(session, "/openApi/swap/v2/quote/depth", {
            "symbol": _sym(symbol), "limit": "5",
        })
        if not isinstance(resp, dict) or resp.get("code") != 0:
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
            "/openApi/swap/v2/user/positions",
            {"symbol": _sym(symbol)},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return []
        result: list[dict[str, Any]] = []
        for p in resp.get("data") or []:
            try:
                pos_amt = float(p.get("positionAmt") or 0)
                if pos_amt == 0:
                    continue
                result.append({
                    "symbol": symbol,
                    "side": "Buy" if pos_amt > 0 else "Sell",
                    "size": abs(pos_amt),
                    "avgPrice": float(p.get("entryPrice") or 0),
                    "unrealisedPnl": float(p.get("unrealizedProfit") or 0),
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
            "/openApi/swap/v2/user/income",
            {"symbol": _sym(symbol), "limit": str(limit), "incomeType": "REALIZED_PNL"},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return []
        result: list[dict[str, Any]] = []
        for t in resp.get("data") or []:
            try:
                result.append({
                    "symbol": symbol,
                    "orderId": str(t.get("tradeId") or ""),
                    "realizedPnl": float(t.get("income") or 0),
                    "qty": 0.0,
                    "price": 0.0,
                    "ts": t.get("time"),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/openApi/swap/v2/trade/allFillOrders",
            {"symbol": _sym(symbol), "orderId": order_id, "limit": str(limit)},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return []
        return resp.get("data") or []

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/openApi/swap/v2/trade/openOrders",
            {"symbol": _sym(symbol)},
            signed=True,
        )
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return []
        return (resp.get("data") or {}).get("orders") or []

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._delete(session, "/openApi/swap/v2/trade/order", {
            "symbol": _sym(symbol), "orderId": order_id,
        })
        if isinstance(resp, dict) and resp.get("code") == 0:
            return resp.get("data")
        return None

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        step = float(info.get("qty_step") or 0.001)
        min_qty = float(info.get("min_qty") or 0.001)
        import math as _math
        rounded = _math.floor(qty / step) * step if step > 0 else qty
        return round(rounded, 6) if rounded >= min_qty else 0.0

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": _sym(symbol)}
        if stop_loss:
            params["stopLoss"] = json.dumps({"type": "MARK_PRICE", "stopPrice": stop_loss})
        if take_profit:
            params["takeProfit"] = json.dumps({"type": "MARK_PRICE", "stopPrice": take_profit})
        return await self._post(session, "/openApi/swap/v2/trade/positionMargin", params)

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
        timeout = post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 30)
        bx_side = "BUY" if side == "Buy" else "SELL"

        ob = await self.get_orderbook_top(session, symbol)
        if not ob:
            return None
        bid, ask = ob
        limit_price = str(ask if bx_side == "BUY" else bid)

        params: dict[str, Any] = {
            "symbol": _sym(symbol),
            "side": bx_side,
            "positionSide": "BOTH",
            "type": "LIMIT",
            "price": limit_price,
            "quantity": str(qty),
            "timeInForce": "PostOnly",
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        resp = await self._post(session, "/openApi/swap/v2/trade/order", params)
        order_id = None
        if isinstance(resp, dict) and resp.get("code") == 0:
            order_data = (resp.get("data") or {}).get("order") or {}
            order_id = str(order_data.get("orderId") or "")

        if order_id:
            await asyncio.sleep(timeout)
            orders = await self.get_open_orders(session, symbol)
            still_open = any(str(o.get("orderId")) == order_id for o in orders)
            if not still_open:
                return {"order_id": order_id, "fill_price": float(limit_price), "fill_qty": qty}
            await self.cancel_order(session, symbol, order_id)

        params_mkt: dict[str, Any] = {
            "symbol": _sym(symbol),
            "side": bx_side,
            "positionSide": "BOTH",
            "type": "MARKET",
            "quantity": str(qty),
        }
        if reduce_only:
            params_mkt["reduceOnly"] = "true"

        resp2 = await self._post(session, "/openApi/swap/v2/trade/order", params_mkt)
        if not isinstance(resp2, dict) or resp2.get("code") != 0:
            print(f"[BINGX] market order fail: {resp2}")
            return None
        mkt_data = (resp2.get("data") or {}).get("order") or {}
        mkt_id = str(mkt_data.get("orderId") or "")
        ob2 = await self.get_orderbook_top(session, symbol)
        fill_price = float(limit_price)
        if ob2:
            fill_price = ob2[1] if bx_side == "BUY" else ob2[0]
        return {"order_id": mkt_id, "fill_price": fill_price, "fill_qty": qty}

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        positions = await self.get_positions(session, symbol)
        results = []
        for pos in positions:
            close_side = "SELL" if pos["side"] == "Buy" else "BUY"
            params = {
                "symbol": _sym(symbol),
                "side": close_side,
                "positionSide": "BOTH",
                "type": "MARKET",
                "quantity": str(pos["size"]),
                "reduceOnly": "true",
            }
            resp = await self._post(session, "/openApi/swap/v2/trade/order", params)
            results.append(resp or {})
        return results

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._get(
            session,
            "/openApi/swap/v2/quote/premiumIndex",
            {"symbol": _sym(symbol)},
        )
        if not isinstance(resp, dict) or resp.get("code") != 0:
            return None
        d = resp.get("data") or {}
        try:
            funding_rate = float(d.get("lastFundingRate") or 0)
            next_ts = int(d.get("nextFundingTime") or 0)
            mark_price = float(d.get("markPrice") or 0)
            return {
                "symbol": symbol,
                "funding_rate": funding_rate,
                "next_funding_ts": next_ts,
                "mark_price": mark_price,
                "interval_hours": 8.0,
            }
        except (TypeError, ValueError):
            return None
