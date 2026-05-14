"""Адаптер MEXC Futures (Contract API v1).

Документация: https://mxcdevelop.github.io/apidocs/contract_v1_en/
Auth: HMAC-SHA256.
  Заголовки: ApiKey, Request-Time (ms), Signature.
  Signature = HMAC-SHA256(api_key + timestamp + params_str_sorted).
Base: https://contract.mexc.com
Символ: BTCUSDT → BTC_USDT (внутренний формат MEXC).

Примечания:
  - Funding меняется каждые collectCycle часов.
  - Объём ордеров в контрактах (vol): 1 контракт = contractSize базовой монеты.
    Для BTC_USDT contractSize = 0.0001 BTC, т.е. 1 контракт ≈ 4.2 USD при BTC=42000.
    vol = round(qty_base / contractSize).
"""
from __future__ import annotations

import asyncio
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

_BASE = "https://contract.mexc.com"
_INSTRUMENT_CACHE: dict[str, dict[str, float]] = {}


def _sym(symbol: str) -> str:
    """BTCUSDT → BTC_USDT."""
    if symbol.endswith("USDT") and "_" not in symbol:
        return symbol[:-4] + "_USDT"
    return symbol


def _round_contracts(qty_base: float, contract_size: float) -> int:
    if contract_size <= 0:
        return 0
    return max(1, round(qty_base / contract_size))


class MEXCAdapter(ExchangeAdapter):
    """MEXC Futures (USDT-settled perpetuals) адаптер."""

    name = "mexc"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET

    def _key(self) -> str:
        return os.getenv("MEXC_API_KEY", "")

    def _secret(self) -> str:
        return os.getenv("MEXC_API_SECRET", "")

    def _sign(self, timestamp: str, params: str = "") -> str:
        pre = self._key() + timestamp + params
        return hmac.new(self._secret().encode(), pre.encode(), hashlib.sha256).hexdigest()

    def _auth_headers(self, params_str: str = "") -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        return {
            "ApiKey": self._key(),
            "Request-Time": ts,
            "Signature": self._sign(ts, params_str),
            "Content-Type": "application/json",
        }

    async def _get(
        self,
        session: Any,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Optional[Any]:
        params_str = urlencode(sorted((params or {}).items()))
        headers = self._auth_headers(params_str) if signed else {}
        try:
            async with session.get(
                _BASE + path, params=params, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[MEXC] GET {path}: {exc}")
            return None

    async def _post(
        self, session: Any, path: str, body: dict[str, Any]
    ) -> Optional[Any]:
        raw = json.dumps(body)
        headers = self._auth_headers(raw)
        try:
            async with session.post(
                _BASE + path, data=raw, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[MEXC] POST {path}: {exc}")
            return None

    async def get_server_time(self, session: Any) -> Optional[int]:
        resp = await self._get(session, "/api/v1/contract/ping")
        if isinstance(resp, dict) and resp.get("success"):
            return int(time.time() * 1000)
        return None

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        resp = await self._get(session, "/api/v1/private/account/assets", signed=True)
        if not isinstance(resp, dict) or not resp.get("success"):
            return None
        for item in resp.get("data") or []:
            if (item.get("currency") or "").upper() == coin.upper():
                try:
                    return float(item.get("availableBalance") or 0)
                except (TypeError, ValueError):
                    return None
        return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        _MAP = {"1": "Min1", "5": "Min5", "15": "Min15", "30": "Min30",
                "60": "Min60", "240": "Hour4", "D": "Day1"}
        mx_interval = _MAP.get(interval, "Min60")
        resp = await self._get(session, f"/api/v1/contract/kline/{_sym(symbol)}", {
            "interval": mx_interval, "limit": limit,
        })
        if not isinstance(resp, dict) or not resp.get("success"):
            return []
        data = resp.get("data") or {}
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        vols = data.get("vol") or []
        times = data.get("time") or []
        result: list[dict[str, Any]] = []
        for i in range(len(closes)):
            try:
                result.append({
                    "ts": int(times[i]) * 1000,
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": float(vols[i]),
                })
            except (IndexError, TypeError, ValueError):
                continue
        return result

    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        mx_sym = _sym(symbol)
        if symbol in _INSTRUMENT_CACHE:
            return _INSTRUMENT_CACHE[symbol]
        resp = await self._get(session, "/api/v1/contract/detail", {"symbol": mx_sym})
        if not isinstance(resp, dict) or not resp.get("success"):
            return None
        d = resp.get("data") or {}
        try:
            contract_size = float(d.get("contractSize") or 1.0)
            min_vol = float(d.get("minVol") or 1.0)
            info: dict[str, float] = {
                "min_qty": contract_size * min_vol,
                "qty_step": contract_size,
                "min_notional": 0.0,
                "tick_size": float(d.get("priceUnit") or 0.01),
                "contract_size": contract_size,
            }
            _INSTRUMENT_CACHE[symbol] = info
            return info
        except (TypeError, ValueError):
            return None

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        resp = await self._get(session, f"/api/v1/contract/depth/{_sym(symbol)}", {
            "limit": 5,
        })
        if not isinstance(resp, dict) or not resp.get("success"):
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
            f"/api/v1/private/position/open_positions",
            {"symbol": _sym(symbol)},
            signed=True,
        )
        if not isinstance(resp, dict) or not resp.get("success"):
            return []
        result: list[dict[str, Any]] = []
        for p in resp.get("data") or []:
            try:
                vol = float(p.get("holdVol") or 0)
                if vol == 0:
                    continue
                ptype = int(p.get("positionType") or 1)
                result.append({
                    "symbol": symbol,
                    "side": "Buy" if ptype == 1 else "Sell",
                    "size": vol * float(p.get("contractSize") or 1.0),
                    "avgPrice": float(p.get("openAvgPrice") or 0),
                    "unrealisedPnl": float(p.get("unrealizedValue") or 0),
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
            "/api/v1/private/position/closed",
            {"symbol": _sym(symbol), "pageNum": 1, "pageSize": limit},
            signed=True,
        )
        if not isinstance(resp, dict) or not resp.get("success"):
            return []
        result: list[dict[str, Any]] = []
        for t in (resp.get("data") or {}).get("resultList") or []:
            try:
                result.append({
                    "symbol": symbol,
                    "orderId": str(t.get("closeOrderId")),
                    "realizedPnl": float(t.get("realised") or 0),
                    "qty": float(t.get("closeVol") or 0),
                    "price": float(t.get("closeAvgPrice") or 0),
                    "ts": t.get("updateTime"),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            f"/api/v1/private/order/deal_details/{order_id}",
            signed=True,
        )
        if not isinstance(resp, dict) or not resp.get("success"):
            return []
        return resp.get("data") or []

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._get(
            session,
            "/api/v1/private/order/list/open_orders/" + _sym(symbol),
            signed=True,
        )
        if not isinstance(resp, dict) or not resp.get("success"):
            return []
        return resp.get("data") or []

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._post(session, "/api/v1/private/order/cancel", {
            "orderId": order_id,
        })
        if isinstance(resp, dict) and resp.get("success"):
            return resp.get("data")
        return None

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        contract_size = float(info.get("contract_size") or 1.0)
        min_qty = float(info.get("min_qty") or contract_size)
        rounded = max(contract_size, contract_size * math.floor(qty / contract_size))
        return rounded if rounded >= min_qty else 0.0

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        return None

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
        info = await self.get_instrument_info(session, symbol)
        contract_size = float((info or {}).get("contract_size") or 0.0001)
        vol = _round_contracts(qty, contract_size)
        if vol == 0:
            return None

        timeout = post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 30)
        is_buy = side == "Buy"

        ob = await self.get_orderbook_top(session, symbol)
        if not ob:
            return None
        bid, ask = ob
        limit_price = ask if is_buy else bid

        # MEXC sides: 1=open long, 2=close short, 3=open short, 4=close long
        if reduce_only:
            mx_side = 4 if is_buy else 2
        else:
            mx_side = 1 if is_buy else 3

        body: dict[str, Any] = {
            "symbol": _sym(symbol),
            "price": limit_price,
            "vol": vol,
            "leverage": int(getattr(config, "ARB_LEVERAGE", 3)),
            "side": mx_side,
            "type": 2,
            "openType": 2,
        }
        resp = await self._post(session, "/api/v1/private/order/submit", body)
        order_id = None
        if isinstance(resp, dict) and resp.get("success"):
            order_id = str(resp.get("data") or "")

        if order_id:
            await asyncio.sleep(timeout)
            orders = await self.get_open_orders(session, symbol)
            still_open = any(str(o.get("orderId")) == order_id for o in orders)
            if not still_open:
                return {"order_id": order_id, "fill_price": limit_price, "fill_qty": qty}
            await self.cancel_order(session, symbol, order_id)

        body_mkt: dict[str, Any] = {
            "symbol": _sym(symbol),
            "vol": vol,
            "leverage": int(getattr(config, "ARB_LEVERAGE", 3)),
            "side": mx_side,
            "type": 5,
            "openType": 2,
        }
        resp2 = await self._post(session, "/api/v1/private/order/submit", body_mkt)
        if not isinstance(resp2, dict) or not resp2.get("success"):
            print(f"[MEXC] market order fail: {resp2}")
            return None
        mkt_id = str(resp2.get("data") or "")
        ob2 = await self.get_orderbook_top(session, symbol)
        fill_price = (ob2[1] if is_buy else ob2[0]) if ob2 else limit_price
        return {"order_id": mkt_id, "fill_price": fill_price, "fill_qty": qty}

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        positions = await self.get_positions(session, symbol)
        results = []
        for pos in positions:
            is_long = pos["side"] == "Buy"
            info = await self.get_instrument_info(session, symbol)
            contract_size = float((info or {}).get("contract_size") or 0.0001)
            vol = _round_contracts(pos["size"], contract_size)
            mx_side = 4 if is_long else 2
            body = {
                "symbol": _sym(symbol),
                "vol": vol,
                "leverage": int(getattr(config, "ARB_LEVERAGE", 3)),
                "side": mx_side,
                "type": 5,
                "openType": 2,
            }
            resp = await self._post(session, "/api/v1/private/order/submit", body)
            results.append(resp or {})
        return results

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        mx_sym = _sym(symbol)
        fund_resp = await self._get(session, f"/api/v1/contract/funding_rate/{mx_sym}")
        ticker_resp = await self._get(session, "/api/v1/contract/ticker", {"symbol": mx_sym})
        if not isinstance(fund_resp, dict) or not fund_resp.get("success"):
            return None
        d = fund_resp.get("data") or {}
        mark_price = 0.0
        if isinstance(ticker_resp, dict) and ticker_resp.get("success"):
            td = ticker_resp.get("data") or {}
            mark_price = float(td.get("fairPrice") or td.get("lastPrice") or 0)
        try:
            funding_rate = float(d.get("fundingRate") or 0)
            next_ts = int(d.get("nextSettleTime") or 0)
            interval_hours = float(d.get("collectCycle") or 8)
            return {
                "symbol": symbol,
                "funding_rate": funding_rate,
                "next_funding_ts": next_ts,
                "mark_price": mark_price,
                "interval_hours": interval_hours,
            }
        except (TypeError, ValueError):
            return None


    async def get_funding_history(
        self,
        session: Any,
        symbol: str,
        since_ms: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Реальные funding-выплаты с MEXC Contract API.

        Endpoint: GET /api/v1/private/funding/records
            ?symbol={mx_sym}&page_size={limit}&start_time={ms}

        Параметры эндпоинта могут варьироваться у MEXC (документация не
        всегда соответствует поведению). При любой ошибке/неудаче парсинга
        возвращаем [] — fallback в executor сработает на аналитическую
        оценку (это нормальный путь, бот не теряет работоспособность).
        """
        mx_sym = _sym(symbol)
        params: dict[str, Any] = {
            "symbol": mx_sym,
            "page_size": max(1, min(100, int(limit))),
            "page_num": 1,
        }
        if since_ms is not None and since_ms > 0:
            params["start_time"] = int(since_ms)
        resp = await self._get(
            session, "/api/v1/private/funding/records", params, signed=True,
        )
        if not isinstance(resp, dict) or not resp.get("success"):
            if isinstance(resp, dict):
                print(f"[MEXC] get_funding_history({symbol}): {resp.get('message') or resp}")
            return []
        # MEXC обычно отдаёт {data: {resultList: [...]}} или {data: [...]}.
        data = resp.get("data") or {}
        if isinstance(data, dict):
            items = data.get("resultList") or data.get("records") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        out: list[dict[str, Any]] = []
        for item in items:
            try:
                ts = int(item.get("settleTime") or item.get("time") or item.get("createTime") or 0)
                funding = float(item.get("funding") or item.get("amount") or 0.0)
            except (TypeError, ValueError):
                continue
            if ts <= 0:
                continue
            out.append({
                "symbol": symbol,
                "ts": ts,
                "funding": funding,
            })
        return out
