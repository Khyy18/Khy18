"""Адаптер Binance USDS-M Futures (линейные перпетуалы, USDT-margin).

Документация: https://binance-docs.github.io/apidocs/futures/en/
Auth: HMAC-SHA256 подпись параметров + X-MBX-APIKEY header.
Testnet: https://testnet.binancefuture.com
Mainnet: https://fapi.binance.com

Поддерживает однонаправленный режим позиций (positionSide=BOTH).
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import time
from typing import Any, Optional
from urllib.parse import urlencode

import config
from .base import ExchangeAdapter

_BASE_MAINNET = "https://fapi.binance.com"
_BASE_TESTNET = "https://testnet.binancefuture.com"

# Кэш instrumentInfo (не меняется пока процесс жив)
_INSTRUMENT_CACHE: dict[str, dict[str, float]] = {}


class BinanceAdapter(ExchangeAdapter):
    """Binance USDS-M Futures адаптер."""

    name = "binance"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET
        self._base = _BASE_TESTNET if self.is_testnet else _BASE_MAINNET

    # ------------------------------------------------------------------ helpers

    def _key(self) -> str:
        return os.getenv("BINANCE_API_KEY", "")

    def _secret(self) -> str:
        return os.getenv("BINANCE_API_SECRET", "")

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = int(time.time() * 1000)
        qs = urlencode(params)
        sig = hmac.new(
            self._secret().encode(), qs.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        return params

    async def _get(
        self,
        session: Any,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Optional[Any]:
        p: dict[str, Any] = dict(params or {})
        if signed:
            p = self._sign(p)
        headers = {}
        if self._key():
            headers["X-MBX-APIKEY"] = self._key()
        try:
            async with session.get(
                self._base + path, params=p, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BINANCE] GET {path}: {exc}")
            return None

    async def _post(
        self, session: Any, path: str, params: dict[str, Any]
    ) -> Optional[Any]:
        p = self._sign(dict(params))
        headers = {"X-MBX-APIKEY": self._key()}
        try:
            async with session.post(
                self._base + path, params=p, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BINANCE] POST {path}: {exc}")
            return None

    async def _delete(
        self, session: Any, path: str, params: dict[str, Any]
    ) -> Optional[Any]:
        p = self._sign(dict(params))
        headers = {"X-MBX-APIKEY": self._key()}
        try:
            async with session.delete(
                self._base + path, params=p, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[BINANCE] DELETE {path}: {exc}")
            return None

    # ------------------------------------------------------- abstract methods

    async def get_server_time(self, session: Any) -> Optional[int]:
        resp = await self._get(session, "/fapi/v1/time")
        if isinstance(resp, dict):
            return resp.get("serverTime")
        return None

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        resp = await self._get(session, "/fapi/v2/balance", signed=True)
        if not isinstance(resp, list):
            return None
        for item in resp:
            if item.get("asset") == coin:
                try:
                    return float(item.get("availableBalance") or item.get("balance") or 0)
                except (TypeError, ValueError):
                    return None
        return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        # Bybit: interval "1"=1m, "60"=1h, "240"=4h, "D"=1d
        _MAP = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1h", "120": "2h", "240": "4h", "360": "6h",
                "480": "8h", "720": "12h", "D": "1d", "W": "1w"}
        bn_interval = _MAP.get(interval, interval)
        resp = await self._get(session, "/fapi/v1/klines", {
            "symbol": symbol, "interval": bn_interval, "limit": limit,
        })
        if not isinstance(resp, list):
            return []
        result: list[dict[str, Any]] = []
        for k in resp:
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
        resp = await self._get(session, "/fapi/v1/exchangeInfo")
        if not isinstance(resp, dict):
            return None
        for s in resp.get("symbols") or []:
            if s.get("symbol") != symbol:
                continue
            try:
                info: dict[str, float] = {}
                for f in s.get("filters") or []:
                    ft = f.get("filterType")
                    if ft == "LOT_SIZE":
                        info["min_qty"] = float(f.get("minQty") or 0)
                        info["qty_step"] = float(f.get("stepSize") or 0)
                    elif ft == "MIN_NOTIONAL":
                        info["min_notional"] = float(f.get("notional") or 0)
                    elif ft == "PRICE_FILTER":
                        info["tick_size"] = float(f.get("tickSize") or 0)
                if info:
                    _INSTRUMENT_CACHE[symbol] = info
                    return info
            except (TypeError, ValueError):
                pass
        return None

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        resp = await self._get(session, "/fapi/v1/depth", {"symbol": symbol, "limit": 5})
        if not isinstance(resp, dict):
            return None
        try:
            bid = float(resp["bids"][0][0])
            ask = float(resp["asks"][0][0])
            return bid, ask
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._get(session, "/fapi/v2/positionRisk",
                               {"symbol": symbol}, signed=True)
        if not isinstance(resp, list):
            return []
        result: list[dict[str, Any]] = []
        for p in resp:
            try:
                size = float(p.get("positionAmt") or 0)
                if size == 0:
                    continue
                result.append({
                    "symbol": p.get("symbol"),
                    "side": "Buy" if size > 0 else "Sell",
                    "size": abs(size),
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
        resp = await self._get(session, "/fapi/v1/userTrades",
                               {"symbol": symbol, "limit": limit}, signed=True)
        if not isinstance(resp, list):
            return []
        result: list[dict[str, Any]] = []
        for t in resp:
            try:
                result.append({
                    "symbol": t.get("symbol"),
                    "orderId": str(t.get("orderId")),
                    "realizedPnl": float(t.get("realizedPnl") or 0),
                    "qty": float(t.get("qty") or 0),
                    "price": float(t.get("price") or 0),
                    "ts": t.get("time"),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._get(session, "/fapi/v1/userTrades",
                               {"symbol": symbol, "orderId": order_id, "limit": limit},
                               signed=True)
        if not isinstance(resp, list):
            return []
        return resp

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
        """PostOnly GTX → IOC Market fallback.

        Сначала пробуем PostOnly (GTX, tif=GTX). Если биржа отвергла —
        сразу MARKET. stop_loss/take_profit игнорируются (отдельные ордера);
        для арба они не нужны.
        """
        bn_side = "BUY" if side.upper() in ("BUY", "LONG") else "SELL"

        # Шаг 1: получить best ask/bid для лимитной цены
        ob = await self.get_orderbook_top(session, symbol)
        if ob:
            best_bid, best_ask = ob
            limit_price = best_ask if bn_side == "BUY" else best_bid
        else:
            limit_price = None

        if limit_price:
            # Попытка PostOnly (GTX)
            info = await self.get_instrument_info(session, symbol)
            tick = float((info or {}).get("tick_size") or 0.01)
            price_str = f"{_round_to_tick(limit_price, tick):.8f}".rstrip("0").rstrip(".")
            params: dict[str, Any] = {
                "symbol": symbol,
                "side": bn_side,
                "type": "LIMIT",
                "timeInForce": "GTX",
                "quantity": qty,
                "price": price_str,
                "reduceOnly": "true" if reduce_only else "false",
            }
            resp = await self._post(session, "/fapi/v1/order", params)
            if isinstance(resp, dict) and resp.get("orderId") and not resp.get("code"):
                timeout = post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 10)
                import asyncio
                await asyncio.sleep(timeout)
                # Проверяем статус
                filled = await self._get(session, "/fapi/v1/order",
                                         {"symbol": symbol, "orderId": resp["orderId"]},
                                         signed=True)
                if isinstance(filled, dict) and filled.get("status") == "FILLED":
                    fill_price = float(filled.get("avgPrice") or limit_price)
                    fill_qty = float(filled.get("executedQty") or qty)
                    return {"orderId": str(resp["orderId"]), "fill_price": fill_price,
                            "fill_qty": fill_qty, "status": "FILLED", "source": "post_only"}
                # Отменяем и падаем на маркет
                await self._delete(session, "/fapi/v1/order",
                                   {"symbol": symbol, "orderId": resp["orderId"]})

        # Шаг 2: MARKET
        market_params: dict[str, Any] = {
            "symbol": symbol,
            "side": bn_side,
            "type": "MARKET",
            "quantity": qty,
            "reduceOnly": "true" if reduce_only else "false",
        }
        resp = await self._post(session, "/fapi/v1/order", market_params)
        if isinstance(resp, dict) and resp.get("orderId") and not resp.get("code"):
            try:
                fill_price = float(resp.get("avgPrice") or resp.get("price") or 0)
                fill_qty = float(resp.get("executedQty") or qty)
            except (TypeError, ValueError):
                fill_price, fill_qty = 0.0, qty
            return {"orderId": str(resp["orderId"]), "fill_price": fill_price,
                    "fill_qty": fill_qty, "status": "FILLED", "source": "market"}
        print(f"[BINANCE] place_order_with_fallback: {resp}")
        return None

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Binance: SL/TP ставятся отдельными STOP_MARKET / TAKE_PROFIT_MARKET ордерами."""
        results: list[dict[str, Any]] = []
        pos = await self.get_positions(session, symbol)
        if not pos:
            return None
        side = pos[0]["side"]
        close_side = "SELL" if side == "Buy" else "BUY"

        for price, order_type in [(stop_loss, "STOP_MARKET"), (take_profit, "TAKE_PROFIT_MARKET")]:
            if price is None:
                continue
            params: dict[str, Any] = {
                "symbol": symbol,
                "side": close_side,
                "type": order_type,
                "stopPrice": price,
                "closePosition": "true",
                "timeInForce": "GTC",
            }
            r = await self._post(session, "/fapi/v1/order", params)
            if isinstance(r, dict):
                results.append(r)
        return {"orders": results} if results else None

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        return await self._delete(session, "/fapi/v1/order",
                                  {"symbol": symbol, "orderId": order_id})

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._get(session, "/fapi/v1/openOrders",
                               {"symbol": symbol}, signed=True)
        if isinstance(resp, list):
            return resp
        return []

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        positions = await self.get_positions(session, symbol)
        results: list[dict[str, Any]] = []
        for p in positions:
            size = float(p.get("size") or 0)
            if size == 0:
                continue
            close_side = "SELL" if p.get("side") == "Buy" else "BUY"
            params: dict[str, Any] = {
                "symbol": symbol,
                "side": close_side,
                "type": "MARKET",
                "quantity": size,
                "reduceOnly": "true",
            }
            r = await self._post(session, "/fapi/v1/order", params)
            if r:
                results.append(r)
        return results

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        min_qty = info.get("min_qty", 0.0)
        step = info.get("qty_step", 0.0)
        min_notional = info.get("min_notional", 0.0)
        if qty < min_qty:
            return 0.0
        if step > 0:
            qty = math.floor(qty / step) * step
            qty = round(qty, 10)
        if min_notional > 0 and qty * price < min_notional:
            return 0.0
        return qty

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        """GET /fapi/v1/premiumIndex — funding rate, mark price, next funding time."""
        resp = await self._get(session, "/fapi/v1/premiumIndex", {"symbol": symbol})
        if not isinstance(resp, dict):
            return None
        try:
            funding_rate = float(resp.get("lastFundingRate") or 0.0)
            next_ts = int(resp.get("nextFundingTime") or 0)
            mark = float(resp.get("markPrice") or 0.0)
        except (TypeError, ValueError) as exc:
            print(f"[BINANCE] get_funding_info({symbol}): парс {exc}")
            return None
        if mark <= 0:
            return None
        return {
            "symbol": symbol,
            "funding_rate": funding_rate,
            "next_funding_ts": next_ts,
            "mark_price": mark,
            "interval_hours": 8.0,  # Binance USDS-M: фиксированный 8h интервал
        }


def _round_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    precision = max(0, round(-math.log10(tick)))
    return round(round(price / tick) * tick, precision)
