"""PostgreSQL-бэкенд хранилища (asyncpg).

Реализует тот же интерфейс, что и SQLiteBackend, но использует asyncpg
и пул соединений. Для продакшн-окружения.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


class PostgresBackend:
    """Async PostgreSQL-бэкенд на asyncpg. Использует пул соединений."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[Any] = None

    async def connect(self) -> None:
        """Создать пул соединений."""
        if asyncpg is None:
            raise ImportError("asyncpg не установлен: pip install asyncpg")
        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)

    async def close(self) -> None:
        """Закрыть пул соединений."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def init_db(self) -> None:
        """Создать таблицы. Идемпотентно."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry DOUBLE PRECISION NOT NULL,
                    exit_price DOUBLE PRECISION,
                    qty DOUBLE PRECISION NOT NULL,
                    pnl DOUBLE PRECISION,
                    ema DOUBLE PRECISION,
                    rsi DOUBLE PRECISION,
                    atr DOUBLE PRECISION,
                    ai_reason TEXT,
                    outcome TEXT NOT NULL DEFAULT 'OPEN',
                    closed_ts TIMESTAMPTZ
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rejected_signals (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL,
                    reason TEXT,
                    confidence INTEGER,
                    context_json JSONB
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rejected_checks (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    filter TEXT NOT NULL,
                    detail TEXT,
                    indicators_json JSONB
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL,
                    equity DOUBLE PRECISION NOT NULL,
                    hwm DOUBLE PRECISION NOT NULL,
                    drawdown DOUBLE PRECISION NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    k TEXT PRIMARY KEY,
                    v JSONB NOT NULL,
                    updated_ts TIMESTAMPTZ NOT NULL
                )
                """
            )

    async def record_trade(
        self,
        symbol: str,
        side: str,
        entry: float,
        qty: float,
        ema_val: Optional[float] = None,
        rsi_val: Optional[float] = None,
        atr_val: Optional[float] = None,
        ai_reason: Optional[str] = None,
        outcome: str = "OPEN",
    ) -> Optional[int]:
        """Сохранить открытую сделку."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO trades
                    (ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason, outcome)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
                """,
                _now_iso(),
                symbol,
                side,
                float(entry),
                float(qty),
                ema_val,
                rsi_val,
                atr_val,
                ai_reason,
                outcome,
            )
            return row["id"] if row else None

    async def update_trade_outcome(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        outcome: str,
    ) -> None:
        """Обновить результат сделки."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE trades
                SET exit_price = $1, pnl = $2, outcome = $3, closed_ts = $4
                WHERE id = $5
                """,
                float(exit_price),
                float(pnl),
                outcome,
                _now_iso(),
                int(trade_id),
            )

    async def record_rejection(
        self,
        reason: str,
        confidence: int,
        ctx: dict[str, Any],
    ) -> None:
        """Сохранить отклонённый сигнал (v1)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rejected_signals (ts, reason, confidence, context_json)
                VALUES ($1, $2, $3, $4)
                """,
                _now_iso(),
                reason,
                int(confidence),
                json.dumps(ctx, ensure_ascii=False),
            )

    async def record_rejected_check(
        self,
        symbol: str,
        filter: str,
        detail: str,
        indicators: Optional[dict[str, Any]] = None,
    ) -> None:
        """Запись детерминированного отклонения (v2)."""
        ind_json = json.dumps(indicators or {}, ensure_ascii=False)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rejected_checks (ts, symbol, filter, detail, indicators_json)
                VALUES ($1, $2, $3, $4, $5)
                """,
                _now_iso(),
                str(symbol or "-"),
                str(filter or "-"),
                str(detail or ""),
                ind_json,
            )

    async def get_recent_errors(self, limit: int = 5) -> list[dict[str, Any]]:
        """Последние убыточные сделки."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, ts, symbol, side, entry, exit_price, qty, pnl, ema, rsi,
                       atr, ai_reason, outcome, closed_ts
                FROM trades
                WHERE outcome = 'LOSS'
                ORDER BY id DESC
                LIMIT $1
                """,
                int(limit),
            )
            return [dict(r) for r in rows]

    async def get_last_rejection(self) -> Optional[dict[str, Any]]:
        """Последний отклонённый ИИ сигнал (v1)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, ts, reason, confidence, context_json
                FROM rejected_signals
                ORDER BY id DESC
                LIMIT 1
                """
            )
            if not row:
                return None
            data = dict(row)
            ctx = data.pop("context_json", None)
            if isinstance(ctx, str):
                try:
                    data["context"] = json.loads(ctx)
                except json.JSONDecodeError:
                    data["context"] = {}
            else:
                data["context"] = ctx or {}
            return data

    async def get_recent_rejected_checks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Последние детерминированные отклонения (v2)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, ts, symbol, filter, detail, indicators_json
                FROM rejected_checks
                ORDER BY id DESC
                LIMIT $1
                """,
                int(limit),
            )
            out: list[dict[str, Any]] = []
            for r in rows:
                data = dict(r)
                ind = data.pop("indicators_json", None)
                if isinstance(ind, str):
                    try:
                        data["indicators"] = json.loads(ind)
                    except json.JSONDecodeError:
                        data["indicators"] = {}
                else:
                    data["indicators"] = ind or {}
                out.append(data)
            return out

    async def get_last_rejected_check(self) -> Optional[dict[str, Any]]:
        """Последнее отклонение v2."""
        rows = await self.get_recent_rejected_checks(limit=1)
        return rows[0] if rows else None

    async def get_open_trades(self) -> list[dict[str, Any]]:
        """Список сделок со статусом OPEN."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason
                FROM trades
                WHERE outcome = 'OPEN'
                ORDER BY id DESC
                """
            )
            return [dict(r) for r in rows]

    async def get_stats(self) -> dict[str, Any]:
        """Сводная статистика."""
        stats = {"count": 0, "wins": 0, "losses": 0, "winrate": 0.0, "pnl_sum": 0.0}
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)                                       AS count,
                    SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
                    COALESCE(SUM(pnl), 0)                          AS pnl_sum
                FROM trades
                WHERE outcome IN ('WIN','LOSS')
                """
            )
            if row:
                wins = int(row["wins"] or 0)
                losses = int(row["losses"] or 0)
                stats["count"] = int(row["count"] or 0)
                stats["wins"] = wins
                stats["losses"] = losses
                stats["pnl_sum"] = float(row["pnl_sum"] or 0.0)
                total = wins + losses
                stats["winrate"] = (wins / total * 100.0) if total else 0.0
        return stats

    async def record_equity(self, equity: float, hwm: float, drawdown: float) -> None:
        """Записать снимок эквити."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO equity_curve (ts, equity, hwm, drawdown)
                VALUES ($1, $2, $3, $4)
                """,
                _now_iso(),
                float(equity),
                float(hwm),
                float(drawdown),
            )

    async def get_equity_curve(self, days: int) -> list[dict[str, Any]]:
        """Снимки эквити за последние days суток."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, ts, equity, hwm, drawdown
                FROM equity_curve
                WHERE ts >= NOW() - make_interval(days => $1)
                ORDER BY id ASC
                """,
                int(days),
            )
            return [dict(r) for r in rows]

    async def get_hwm(self) -> float:
        """Наибольший HWM за всё время."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(hwm), 0.0) AS v FROM equity_curve"
            )
            return float(row["v"]) if row else 0.0

    async def get_current_drawdown(self) -> float:
        """Просадка последнего снимка."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT drawdown
                FROM equity_curve
                ORDER BY id DESC
                LIMIT 1
                """
            )
            return float(row["drawdown"]) if row else 0.0

    async def get_trades_since(self, days: int) -> list[dict[str, Any]]:
        """Все сделки за последние days суток."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, ts, symbol, side, entry, exit_price, qty, pnl, ema, rsi,
                       atr, ai_reason, outcome, closed_ts
                FROM trades
                WHERE ts >= NOW() - make_interval(days => $1)
                ORDER BY id ASC
                """,
                int(days),
            )
            return [dict(r) for r in rows]

    async def get_week_pnl(self) -> float:
        """Сумма pnl за последние 7 суток."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(pnl), 0.0) AS v
                FROM trades
                WHERE closed_ts IS NOT NULL
                  AND closed_ts >= NOW() - INTERVAL '7 days'
                """
            )
            return float(row["v"]) if row else 0.0

    async def kv_set(self, key: str, value: Any) -> None:
        """Записать значение в kv_store."""
        payload = json.dumps(value, ensure_ascii=False, default=str)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kv_store (k, v, updated_ts) VALUES ($1, $2, $3)
                ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v, updated_ts=EXCLUDED.updated_ts
                """,
                str(key),
                payload,
                _now_iso(),
            )

    async def kv_get(self, key: str, default: Any = None) -> Any:
        """Прочитать значение из kv_store."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT v FROM kv_store WHERE k = $1", str(key)
            )
            if not row:
                return default
            val = row["v"]
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return default
            return val
