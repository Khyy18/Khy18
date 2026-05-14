"""Адаптер Gate.io Futures (USDT-margined linear perpetuals).

Документация: https://www.gate.io/docs/developers/futures/en/
Auth: HMAC-SHA512. Каждый подписанный запрос несёт заголовки
  KEY, Timestamp, SIGN = hmac_sha512(method+\n+path+\n+qs+\n+body_hash+\n+ts).

Settle: "usdt" (USDT-маржинальные перпы).
Формат символа: "BTCUSDT" (входящий) → "BTC_USDT" (Gate.io внутренний).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from typing import Any, Optional

import config
from .base import ExchangeAdapter

_BASE = "https://api.gateio.ws"
_SETTLE = "usdt"

# Кэш contractInfo (не меняется пока процесс жив)
_CONTRACT_CACHE: dict[str, dict[str, Any]] = {}


def _sym_to_contract(symbol: str) -> str:
    """BTCUSDT → BTC_USDT  (удаляем USDT суффикс, вставляем '_')."""
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}_USDT"
    return symbol


def _round_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    precision = max(0, round(-math.log10(tick)))
    return round(round(price / tick) * tick, precision)


class GateAdapter(ExchangeAdapter):
    """Gate.io USDT-settled linear perpetuals adapter."""

    name = "gate"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET

    # ------------------------------------------------------------------ helpers

    def _key(self) -> str:
        return os.getenv("GATE_API_KEY", "")

    def _secret(self) -> str:
        return os.getenv("GATE_API_SECRET", "")

    def _sign_headers(
        self, method: str, path: str, query: str = "", body: str = ""
    ) -> dict[str, str]:
        ts = str(int(time.time()))
        body_hash = hashlib.sha512(body.encode()).hexdigest()
        msg = f"{method}\n{path}\n{query}\n{body_hash}\n{ts}"
        sig = hmac.new(
            self._secret().encode(), msg.encode(), hashlib.sha512
        ).hexdigest()
        return {
            "KEY": self._key(),
            "Timestamp": ts,
            "SIGN": sig,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get(
        self,
        session: Any,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Optional[Any]:
        from urllib.parse import urlencode
        qs = urlencode(params) if params else ""
        full_path = path
        url = _BASE + path + (f"?{qs}" if qs else "")
        headers: dict[str, str] = {"Accept": "application/json"}
        if signed:
            headers = self._sign_headers("GET", full_path, qs)
        try:
            async with session.get(url, headers=headers) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[GATE] GET {path}: {exc}")
            return None

    async def _post(
        self, session: Any, path: str, body: dict[str, Any]
    ) -> Optional[Any]:
        body_str = json.dumps(body)
        headers = self._sign_headers("POST", path, "", body_str)
        try:
            async with session.post(
                _BASE + path, data=body_str, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[GATE] POST {path}: {exc}")
            return None

    async def _delete(
        self, session: Any, path: str, params: Optional[dict[str, Any]] = None
    ) -> Optional[Any]:
        from urllib.parse import urlencode
        qs = urlencode(params) if params else ""
        headers = self._sign_headers("DELETE", path, qs)
        url = _BASE + path + (f"?{qs}" if qs else "")
        try:
            async with session.delete(url, headers=headers) as resp:
                return await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            print(f"[GATE] DELETE {path}: {exc}")
            return None

    async def _get_contract_info(
        self, session: Any, contract: str
    ) -> Optional[dict[str, Any]]:
        if contract in _CONTRACT_CACHE:
            return _CONTRACT_CACHE[contract]
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/contracts/{contract}")
        if isinstance(resp, dict) and resp.get("name"):
            _CONTRACT_CACHE[contract] = resp
            return resp
        return None

    # ------------------------------------------------------- abstract methods

    async def get_server_time(self, session: Any) -> Optional[int]:
        resp = await self._get(session, "/api/v4/futures/usdt/contracts",
                               {"limit": 1})
        # Gate.io не имеет /time, используем локальное время
        return int(time.time() * 1000)

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/accounts", signed=True)
        if not isinstance(resp, dict):
            return None
        try:
            return float(resp.get("available") or resp.get("total") or 0)
        except (TypeError, ValueError):
            return None

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        contract = _sym_to_contract(symbol)
        # Gate.io intervals: 10s,30s,1m,5m,15m,30m,1h,4h,8h,1d,7d,30d
        _MAP = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1h", "120": "2h", "240": "4h", "360": "6h",
                "480": "8h", "720": "12h", "D": "1d", "W": "7d"}
        gt_interval = _MAP.get(interval, "1h")
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/candlesticks", {
            "contract": contract, "interval": gt_interval, "limit": limit,
        })
        if not isinstance(resp, list):
            return []
        result: list[dict[str, Any]] = []
        for k in resp:
            try:
                result.append({
                    "ts": int(k.get("t") or k.get("time") or 0) * 1000,
                    "open": float(k.get("o") or 0),
                    "high": float(k.get("h") or 0),
                    "low": float(k.get("l") or 0),
                    "close": float(k.get("c") or 0),
                    "volume": float(k.get("v") or 0),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        contract = _sym_to_contract(symbol)
        info = await self._get_contract_info(session, contract)
        if not info:
            return None
        try:
            step = float(info.get("order_size_min") or 1)
            quanto = float(info.get("quanto_multiplier") or 0.0001)
            tick = float(info.get("order_price_round") or 0.01)
            return {
                "min_qty": quanto * step,       # в базовом активе
                "qty_step": quanto,              # шаг = 1 контракт в BTC
                "min_notional": 0.0,
                "tick_size": tick,
                "quanto_multiplier": quanto,     # extra field для конвертации
            }
        except (TypeError, ValueError):
            return None

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        contract = _sym_to_contract(symbol)
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/order_book", {
            "contract": contract, "limit": 1, "with_id": "false",
        })
        if not isinstance(resp, dict):
            return None
        try:
            bid = float((resp.get("bids") or [[0]])[0][0])
            ask = float((resp.get("asks") or [[0]])[0][0])
            return bid, ask
        except (IndexError, TypeError, ValueError):
            return None

    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        contract = _sym_to_contract(symbol)
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/positions/{contract}",
                               signed=True)
        if not isinstance(resp, dict) or not resp.get("contract"):
            return []
        try:
            size_contracts = int(resp.get("size") or 0)
            if size_contracts == 0:
                return []
            quanto = float(resp.get("quanto_multiplier") or 0.0001)
            size_base = abs(size_contracts) * quanto
            entry = float(resp.get("entry_price") or 0)
            upnl = float(resp.get("unrealised_pnl") or 0)
            return [{
                "symbol": symbol,
                "side": "Buy" if size_contracts > 0 else "Sell",
                "size": size_base,
                "avgPrice": entry,
                "unrealisedPnl": upnl,
                "markPrice": float(resp.get("mark_price") or 0),
            }]
        except (TypeError, ValueError):
            return []

    async def get_closed_pnl(
        self, session: Any, symbol: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        contract = _sym_to_contract(symbol)
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/my_trades", {
            "contract": contract, "limit": limit,
        }, signed=True)
        if not isinstance(resp, list):
            return []
        result: list[dict[str, Any]] = []
        for t in resp:
            try:
                result.append({
                    "symbol": symbol,
                    "orderId": str(t.get("order_id")),
                    "realizedPnl": float(t.get("realised_pnl") or 0),
                    "qty": abs(int(t.get("size") or 0)),
                    "price": float(t.get("price") or 0),
                    "ts": t.get("create_time_ms"),
                })
            except (TypeError, ValueError):
                continue
        return result

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        contract = _sym_to_contract(symbol)
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/my_trades", {
            "contract": contract, "order": order_id, "limit": limit,
        }, signed=True)
        if isinstance(resp, list):
            return resp
        return []

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
        """PostOnly (poc) → IOC (ioc) market fallback.

        Gate.io size = кол-во контрактов (знак определяет направление).
        qty — в базовом активе (BTC, ETH...), конвертируем в контракты.
        """
        contract = _sym_to_contract(symbol)
        info = await self._get_contract_info(session, contract)
        quanto = float((info or {}).get("quanto_multiplier") or 0.0001)
        size_contracts = int(round(qty / quanto))
        if size_contracts == 0:
            print(f"[GATE] place_order: qty {qty} → 0 contracts, пропуск")
            return None

        # Gate.io: положительный size = Long, отрицательный = Short
        is_buy = side.upper() in ("BUY", "LONG")
        if reduce_only:
            # При закрытии знак обратный текущей позиции
            is_buy = not is_buy
        signed_size = size_contracts if is_buy else -size_contracts

        # Шаг 1: PostOnly (price=0 при tif=poc запрещён; берём best bid/ask)
        ob = await self.get_orderbook_top(session, symbol)
        tick = float((info or {}).get("order_price_round") or 0.01)

        if ob:
            best_bid, best_ask = ob
            limit_price = _round_to_tick(best_ask if is_buy else best_bid, tick)
            body: dict[str, Any] = {
                "contract": contract,
                "size": signed_size,
                "price": str(limit_price),
                "tif": "poc",
                "reduce_only": reduce_only,
            }
            resp = await self._post(session, f"/api/v4/futures/{_SETTLE}/orders", body)
            if isinstance(resp, dict) and resp.get("id") and not resp.get("label"):
                import asyncio
                timeout = post_only_timeout_sec or getattr(config, "POST_ONLY_TIMEOUT_SEC", 10)
                await asyncio.sleep(timeout)
                # Проверяем статус ордера
                order_status = await self._get(
                    session,
                    f"/api/v4/futures/{_SETTLE}/orders/{resp['id']}",
                    signed=True,
                )
                if isinstance(order_status, dict) and order_status.get("status") == "finished":
                    fill_qty = abs(int(order_status.get("size", size_contracts))) * quanto
                    fill_price = float(order_status.get("fill_price") or limit_price)
                    return {"orderId": str(resp["id"]), "fill_price": fill_price,
                            "fill_qty": fill_qty, "status": "FILLED", "source": "post_only"}
                # Отменяем незаполненный ордер
                await self._delete(session, f"/api/v4/futures/{_SETTLE}/orders/{resp['id']}")

        # Шаг 2: IOC (market-like)
        market_body: dict[str, Any] = {
            "contract": contract,
            "size": signed_size,
            "price": "0",  # market price
            "tif": "ioc",
            "reduce_only": reduce_only,
        }
        resp = await self._post(session, f"/api/v4/futures/{_SETTLE}/orders", market_body)
        if isinstance(resp, dict) and resp.get("id") and not resp.get("label"):
            fill_price = float(resp.get("fill_price") or ob[0] if ob else 0)
            fill_qty = abs(int(resp.get("size") or size_contracts)) * quanto
            return {"orderId": str(resp["id"]), "fill_price": fill_price,
                    "fill_qty": fill_qty, "status": "FILLED", "source": "market"}
        print(f"[GATE] place_order_with_fallback: {resp}")
        return None

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Gate.io: SL/TP через price_triggered orders (POST /orders)."""
        pos = await self.get_positions(session, symbol)
        if not pos:
            return None
        contract = _sym_to_contract(symbol)
        info = await self._get_contract_info(session, contract)
        quanto = float((info or {}).get("quanto_multiplier") or 0.0001)
        size_contracts = int(round(float(pos[0].get("size") or 0) / quanto))
        close_size = -size_contracts if pos[0]["side"] == "Buy" else size_contracts

        results: list[Any] = []
        for trigger_price, order_type in [(stop_loss, "close-long-position"),
                                          (take_profit, "close-long-position")]:
            if trigger_price is None:
                continue
            body = {
                "initial": {"contract": contract, "size": close_size,
                            "price": "0", "tif": "ioc", "reduce_only": True},
                "trigger": {"strategy_type": 0, "price_type": 0,
                            "price": str(trigger_price),
                            "rule": 1 if order_type == "close-long-position" else 2},
            }
            r = await self._post(session,
                                  f"/api/v4/futures/{_SETTLE}/price_orders", body)
            results.append(r)
        return {"orders": results} if results else None

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        contract = _sym_to_contract(symbol)
        return await self._delete(session,
                                   f"/api/v4/futures/{_SETTLE}/orders/{order_id}",
                                   {"contract": contract})

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        contract = _sym_to_contract(symbol)
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/orders", {
            "contract": contract, "status": "open",
        }, signed=True)
        if isinstance(resp, list):
            return resp
        return []

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        positions = await self.get_positions(session, symbol)
        results: list[dict[str, Any]] = []
        for p in positions:
            size_base = float(p.get("size") or 0)
            if size_base == 0:
                continue
            contract = _sym_to_contract(symbol)
            info = await self._get_contract_info(session, contract)
            quanto = float((info or {}).get("quanto_multiplier") or 0.0001)
            size_c = int(round(size_base / quanto))
            # Закрытие: обратный знак
            close_size = -size_c if p["side"] == "Buy" else size_c
            body: dict[str, Any] = {
                "contract": contract,
                "size": close_size,
                "price": "0",
                "tif": "ioc",
                "reduce_only": True,
            }
            r = await self._post(session, f"/api/v4/futures/{_SETTLE}/orders", body)
            if r:
                results.append(r)
        return results

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        quanto = info.get("quanto_multiplier", 0.0001)
        if quanto <= 0:
            return 0.0
        min_contracts = int(info.get("min_qty", 0) / quanto) or 1
        contracts = int(math.floor(qty / quanto))
        if contracts < min_contracts:
            return 0.0
        return contracts * quanto

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        """GET /futures/usdt/contracts/{contract} → funding_rate, funding_next_apply."""
        contract = _sym_to_contract(symbol)
        resp = await self._get_contract_info(session, contract)
        # Свежий запрос — сбрасываем кэш чтобы получить актуальный funding rate
        _CONTRACT_CACHE.pop(contract, None)
        resp = await self._get(session, f"/api/v4/futures/{_SETTLE}/contracts/{contract}")
        if not isinstance(resp, dict):
            return None
        try:
            funding_rate = float(resp.get("funding_rate") or 0.0)
            next_apply = int(resp.get("funding_next_apply") or 0) * 1000  # секунды → ms
            mark = float(resp.get("mark_price") or resp.get("last_price") or 0.0)
            interval_sec = int(resp.get("funding_interval") or 28800)
            interval_hours = interval_sec / 3600
        except (TypeError, ValueError) as exc:
            print(f"[GATE] get_funding_info({symbol}): парс {exc}")
            return None
        if mark <= 0:
            return None
        return {
            "symbol": symbol,
            "funding_rate": funding_rate,
            "next_funding_ts": next_apply,
            "mark_price": mark,
            "interval_hours": interval_hours,
        }
