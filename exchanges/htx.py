"""Адаптер HTX (Huobi) Linear Swap — USDT-margined perpetuals.

Документация: https://huobiapi.github.io/docs/usdt_swap/v1/en/
Auth: HMAC-SHA256 URL-параметры.
  GET:  подпись в query string (AccessKeyId, SignatureMethod, SignatureVersion, Timestamp, Signature).
  POST: подпись в query string, тело как JSON.
  pre_hash = METHOD + "\\n" + HOST + "\\n" + PATH + "\\n" + sorted_params_urlencoded
  Signature = base64(HMAC-SHA256(secret, pre_hash)).
Base: https://api.hbdm.com
Символ: BTCUSDT → BTC-USDT (внутренний формат HTX).
Контракт: 0.01 BTC/contract (из swap_contract_info).
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
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote, urlencode

import config
from .base import ExchangeAdapter

_BASE = "https://api.hbdm.com"
_HOST = "api.hbdm.com"
_INSTRUMENT_CACHE: dict[str, dict[str, float]] = {}


def _sym(symbol: str) -> str:
    """BTCUSDT → BTC-USDT."""
    if symbol.endswith("USDT") and "-" not in symbol:
        return symbol[:-4] + "-USDT"
    return symbol


def _utc_ts() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _build_auth_params(
    api_key: str, api_secret: str, method: str, path: str,
    extra: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    params: dict[str, str] = {
        "AccessKeyId": api_key,
        "SignatureMethod": "HmacSHA256",
        "SignatureVersion": "2",
        "Timestamp": _utc_ts(),
    }
    if extra:
        params.update(extra)
    sorted_qs = "&".join(
        f"{k}={quote(str(params[k]), safe='')}" for k in sorted(params)
    )
    pre_hash = f"{method.upper()}\n{_HOST}\n{path}\n{sorted_qs}"
    raw = hmac.new(api_secret.encode(), pre_hash.encode(), hashlib.sha256).digest()
    params["Signature"] = base64.b64encode(raw).decode()
    return params


def _round_contracts(qty_base: float, contract_size: float) -> int:
    if contract_size <= 0:
        return 0
    return max(1, round(qty_base / contract_size))


class HTXAdapter(ExchangeAdapter):
    """HTX (Huobi) Linear Swap USDT-M адаптер."""

    name = "htx"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET

    def _key(self) -> str:
        return os.getenv("HTX_API_KEY", "")

    def _secret(self) -> str:
        return os.getenv("HTX_API_SECRET", "")

    async def _get(
        self,
        session: Any,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Optional[Any]:
        qparams: dict[str, Any] = dict(params or {})
        if signed:
            auth = _build_auth_params(self._key(), self._secret(), "GET", path)
            qparams.update(auth)
        try:
            async with session.get(_BASE + path, params=qparams) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[HTX] GET {path}: {exc}")
            return None

    async def _post(
        self, session: Any, path: str, body: dict[str, Any]
    ) -> Optional[Any]:
        auth = _build_auth_params(self._key(), self._secret(), "POST", path)
        raw = json.dumps(body)
        try:
            async with session.post(
                _BASE + path,
                params=auth,
                data=raw,
                headers={"Content-Type": "application/json"},
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[HTX] POST {path}: {exc}")
            return None

    async def get_server_time(self, session: Any) -> Optional[int]:
        return int(time.time() * 1000)

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        resp = await self._post(
            session, "/linear-swap-api/v1/swap_cross_account_info", {}
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return None
        for item in resp.get("data") or []:
            if (item.get("margin_asset") or "").upper() == coin.upper():
                try:
                    return float(item.get("margin_available") or item.get("margin_balance") or 0)
                except (TypeError, ValueError):
                    return None
        return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        _MAP = {"1": "1min", "5": "5min", "15": "15min", "30": "30min",
                "60": "60min", "240": "4hour", "D": "1day"}
        htx_period = _MAP.get(interval, "60min")
        resp = await self._get(session, "/linear-swap-ex/market/history/kline", {
            "contract_code": _sym(symbol), "period": htx_period, "size": limit,
        })
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return []
        result: list[dict[str, Any]] = []
        for k in resp.get("data") or []:
            try:
                result.append({
                    "ts": int(k.get("id", 0)) * 1000,
                    "open": float(k["open"]),
                    "high": float(k["high"]),
                    "low": float(k["low"]),
                    "close": float(k["close"]),
                    "volume": float(k["vol"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        return result

    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        if symbol in _INSTRUMENT_CACHE:
            return _INSTRUMENT_CACHE[symbol]
        resp = await self._get(
            session,
            "/linear-swap-api/v1/swap_contract_info",
            {"contract_code": _sym(symbol)},
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return None
        for d in resp.get("data") or []:
            if d.get("contract_code") != _sym(symbol):
                continue
            try:
                info: dict[str, float] = {
                    "min_qty": float(d.get("contract_size") or 0.01),
                    "qty_step": float(d.get("contract_size") or 0.01),
                    "min_notional": 0.0,
                    "tick_size": float(d.get("price_tick") or 0.01),
                    "contract_size": float(d.get("contract_size") or 0.01),
                }
                _INSTRUMENT_CACHE[symbol] = info
                return info
            except (TypeError, ValueError):
                pass
        return None

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        resp = await self._get(session, "/linear-swap-ex/market/depth", {
            "contract_code": _sym(symbol), "type": "step0",
        })
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return None
        tick = resp.get("tick") or {}
        try:
            bid = float(tick["bids"][0][0])
            ask = float(tick["asks"][0][0])
            return bid, ask
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._post(
            session,
            "/linear-swap-api/v1/swap_cross_position_info",
            {"contract_code": _sym(symbol)},
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return []
        result: list[dict[str, Any]] = []
        for p in resp.get("data") or []:
            try:
                volume = float(p.get("volume") or 0)
                if volume == 0:
                    continue
                direction = str(p.get("direction") or "buy")
                contract_size = float(p.get("contract_size") or 0.01)
                result.append({
                    "symbol": symbol,
                    "side": "Buy" if direction == "buy" else "Sell",
                    "size": volume * contract_size,
                    "avgPrice": float(p.get("cost_open") or 0),
                    "unrealisedPnl": float(p.get("profit_unreal") or 0),
                    "markPrice": float(p.get("last_price") or 0),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_closed_pnl(
        self, session: Any, symbol: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._post(
            session,
            "/linear-swap-api/v1/swap_financial_record",
            {"contract_code": _sym(symbol), "type": "3,4", "create_date": 7, "page_size": limit},
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return []
        result: list[dict[str, Any]] = []
        for t in (resp.get("data") or {}).get("financial_record") or []:
            try:
                result.append({
                    "symbol": symbol,
                    "orderId": str(t.get("id")),
                    "realizedPnl": float(t.get("amount") or 0),
                    "qty": 0.0,
                    "price": 0.0,
                    "ts": t.get("ts"),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        resp = await self._post(
            session,
            "/linear-swap-api/v1/swap_cross_matchresults",
            {"contract_code": _sym(symbol), "order_id": order_id},
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return []
        return (resp.get("data") or {}).get("trades") or []

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        resp = await self._post(
            session,
            "/linear-swap-api/v1/swap_cross_openorders",
            {"contract_code": _sym(symbol)},
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return []
        return (resp.get("data") or {}).get("orders") or []

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._post(
            session,
            "/linear-swap-api/v1/swap_cross_cancel",
            {"contract_code": _sym(symbol), "order_id": order_id},
        )
        if isinstance(resp, dict) and resp.get("status") == "ok":
            return resp.get("data")
        return None

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        contract_size = float(info.get("contract_size") or 0.01)
        min_qty = float(info.get("min_qty") or contract_size)
        contracts = math.floor(qty / contract_size)
        if contracts < 1:
            return 0.0
        result = contracts * contract_size
        return result if result >= min_qty else 0.0

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
        contract_size = float((info or {}).get("contract_size") or 0.01)
        vol = _round_contracts(qty, contract_size)
        if vol == 0:
            return None

        timeout = post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 30)
        is_buy = side == "Buy"
        direction = "buy" if is_buy else "sell"
        offset = "close" if reduce_only else "open"

        ob = await self.get_orderbook_top(session, symbol)
        if not ob:
            return None
        bid, ask = ob
        limit_price = ask if is_buy else bid

        body: dict[str, Any] = {
            "contract_code": _sym(symbol),
            "volume": vol,
            "direction": direction,
            "offset": offset,
            "lever_rate": int(getattr(config, "ARB_LEVERAGE", 3)),
            "order_price_type": "post_only",
            "price": limit_price,
        }
        resp = await self._post(
            session, "/linear-swap-api/v1/swap_cross_order", body
        )
        order_id = None
        if isinstance(resp, dict) and resp.get("status") == "ok":
            order_id = str((resp.get("data") or {}).get("order_id") or "")

        if order_id:
            await asyncio.sleep(timeout)
            orders = await self.get_open_orders(session, symbol)
            still_open = any(str(o.get("order_id")) == order_id for o in orders)
            if not still_open:
                return {"order_id": order_id, "fill_price": limit_price, "fill_qty": qty}
            await self.cancel_order(session, symbol, order_id)

        body_mkt: dict[str, Any] = {
            "contract_code": _sym(symbol),
            "volume": vol,
            "direction": direction,
            "offset": offset,
            "lever_rate": int(getattr(config, "ARB_LEVERAGE", 3)),
            "order_price_type": "market",
        }
        resp2 = await self._post(
            session, "/linear-swap-api/v1/swap_cross_order", body_mkt
        )
        if not isinstance(resp2, dict) or resp2.get("status") != "ok":
            print(f"[HTX] market order fail: {resp2}")
            return None
        mkt_id = str((resp2.get("data") or {}).get("order_id") or "")
        ob2 = await self.get_orderbook_top(session, symbol)
        fill_price = (ob2[1] if is_buy else ob2[0]) if ob2 else limit_price
        return {"order_id": mkt_id, "fill_price": fill_price, "fill_qty": qty}

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        positions = await self.get_positions(session, symbol)
        results = []
        for pos in positions:
            info = await self.get_instrument_info(session, symbol)
            contract_size = float((info or {}).get("contract_size") or 0.01)
            vol = _round_contracts(pos["size"], contract_size)
            direction = "sell" if pos["side"] == "Buy" else "buy"
            body = {
                "contract_code": _sym(symbol),
                "volume": vol,
                "direction": direction,
                "offset": "close",
                "lever_rate": int(getattr(config, "ARB_LEVERAGE", 3)),
                "order_price_type": "market",
            }
            resp = await self._post(
                session, "/linear-swap-api/v1/swap_cross_order", body
            )
            results.append(resp or {})
        return results

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        resp = await self._get(
            session,
            "/linear-swap-api/v1/swap_funding_rate",
            {"contract_code": _sym(symbol)},
        )
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return None
        data_list = resp.get("data") or []
        d = data_list[0] if data_list else {}
        ticker_resp = await self._get(
            session,
            "/linear-swap-ex/market/detail/merged",
            {"contract_code": _sym(symbol)},
        )
        mark_price = 0.0
        if isinstance(ticker_resp, dict) and ticker_resp.get("status") == "ok":
            tick = ticker_resp.get("tick") or {}
            mark_price = float(tick.get("close") or 0)
        try:
            funding_rate = float(d.get("funding_rate") or 0)
            next_ts_raw = d.get("next_funding_time") or d.get("settlement_time") or 0
            next_ts = int(next_ts_raw) if next_ts_raw else 0
            return {
                "symbol": symbol,
                "funding_rate": funding_rate,
                "next_funding_ts": next_ts,
                "mark_price": mark_price,
                "interval_hours": 8.0,
            }
        except (TypeError, ValueError):
            return None
