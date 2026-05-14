"""Хранилище состояния торгового бота на SQLite (stdlib sqlite3).

Таблицы:
  - trades:           история сделок, их результат и контекст индикаторов.
                      Колонка closed_ts добавляется миграцией при запуске.
  - rejected_signals: v1 - сигналы, отклонённые старым ИИ-гейтом (сохраняем
                      для обратной совместимости, но новый код не пишет).
  - rejected_checks:  v2 - отклонения по детерминированным фильтрам
                      (Donchian, режим, blackout и т.п.).
  - equity_curve:     снимки эквити, HWM и текущей просадки - ряд для
                      расчёта MAX_WEEKLY_LOSS / MAX_DRAWDOWN и графиков.
  - ai_gate_log:      v3 - журнал решений AI-veto gate (approve/veto/error)
                      по каждому намерению открыть сделку. Флаг `applied`
                      показывает, было ли решение фактически применено
                      (только в active-режиме для veto/error).
  - symbol_blocks:    v3 - запретный список (manual + auto) с окончанием
                      по until_iso (NULL = бессрочно). Manual ставится из
                      Telegram, auto - после N подряд LOSS на символе.

Инициализация схемы (включая идемпотентную миграцию trades.closed_ts)
выполняется при импорте модуля (init_db()).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


# Путь к SQLite trades.db.
# Приоритет: TRADES_DB_PATH (env) -> /app/data/trades[_real].db если такой
# каталог смонтирован (persistent volume на Fly.io/Docker) -> рядом с
# memory.py (локальный запуск). Это даёт плавный переход между dev и prod
# без правок кода: на Fly.io монтируем volume на /app/data и переменную
# не трогаем.
#
# Суффикс выбирается по IS_TESTNET: демо пишет в trades.db, реал - в
# trades_real.db. История не должна смешиваться: MDD-трекинг, daily/weekly
# PnL и статистика винрейта считаются отдельно для каждого аккаунта.
# Если TRADES_DB_PATH задан явно в env - уважаем выбор пользователя,
# режим не учитываем.
def _resolve_db_path() -> str:
    env_path = os.getenv("TRADES_DB_PATH", "").strip()
    if env_path:
        return env_path
    # Импорт config внутри функции: модуль memory иногда импортируется
    # до полной инициализации config (например в тестах). Импорт лениво
    # безопаснее, чем module-level.
    try:
        import config as _cfg  # noqa: PLC0415
        is_testnet = bool(getattr(_cfg, "IS_TESTNET", True))
    except Exception:  # noqa: BLE001
        is_testnet = True
    suffix = "trades.db" if is_testnet else "trades_real.db"
    persistent_dir = "/app/data"
    if os.path.isdir(persistent_dir) and os.access(persistent_dir, os.W_OK):
        return os.path.join(persistent_dir, suffix)
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), suffix
    )


DB_PATH = _resolve_db_path()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _ensure_trades_closed_ts(conn: sqlite3.Connection) -> None:
    """Идемпотентно добавить колонку closed_ts в таблицу trades."""
    try:
        rows = conn.execute("PRAGMA table_info('trades')").fetchall()
        cols = {r[1] for r in rows}
        if "closed_ts" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN closed_ts TEXT")
    except sqlite3.Error as exc:
        # Не ломаем запуск - просто логируем и продолжаем со старой схемой.
        print(f"[MEMORY] Не удалось добавить колонку closed_ts: {exc}")


def init_db() -> None:
    """Создать таблицы и применить лёгкие миграции. Идемпотентно."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry REAL NOT NULL,
                    exit REAL,
                    qty REAL NOT NULL,
                    pnl REAL,
                    ema REAL,
                    rsi REAL,
                    atr REAL,
                    ai_reason TEXT,
                    outcome TEXT NOT NULL DEFAULT 'OPEN',
                    closed_ts TEXT
                )
                """
            )
            _ensure_trades_closed_ts(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rejected_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    reason TEXT,
                    confidence INTEGER,
                    context_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rejected_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    filter TEXT NOT NULL,
                    detail TEXT,
                    indicators_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    equity REAL NOT NULL,
                    hwm REAL NOT NULL,
                    drawdown REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_gate_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    strategy TEXT,
                    verdict TEXT NOT NULL,
                    reason TEXT,
                    confidence INTEGER,
                    applied INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    type TEXT NOT NULL,
                    until_iso TEXT,
                    reason TEXT,
                    added_iso TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_symbol_blocks_symbol
                ON symbol_blocks(symbol)
                """
            )
            conn.commit()
        print(f"[MEMORY] База данных trades.db инициализирована: {DB_PATH}")
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка инициализации БД: {exc}")


def record_trade(
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
    """Сохранить открытую сделку. Возвращает id созданной записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trades
                    (ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason,
                     outcome, closed_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
                    None,
                ),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать сделку: {exc}")
        return None


def update_trade_outcome(
    trade_id: int,
    exit_price: float,
    pnl: float,
    outcome: str,
) -> None:
    """Обновить результат сделки (WIN/LOSS/OPEN). Ставит closed_ts = сейчас."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET exit = ?, pnl = ?, outcome = ?, closed_ts = ?
                WHERE id = ?
                """,
                (
                    float(exit_price),
                    float(pnl),
                    outcome,
                    _now_iso(),
                    int(trade_id),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось обновить сделку #{trade_id}: {exc}")


def record_rejection(
    reason: str,
    confidence: int,
    ctx: dict[str, Any],
) -> None:
    """Сохранить отклонённый сигнал (старая v1-таблица). Сохраняем для
    обратной совместимости - новый код пишет в rejected_checks."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO rejected_signals (ts, reason, confidence, context_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    reason,
                    int(confidence),
                    json.dumps(ctx, ensure_ascii=False),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать отклонённый сигнал: {exc}")


def record_rejected_check(
    symbol: str,
    filter: str,  # noqa: A002 (специально совпадает с именем колонки)
    detail: str,
    indicators: Optional[dict[str, Any]] = None,
) -> None:
    """v2: запись детерминированного отклонения (Donchian, blackout, режим).

    Используется strategy_v2/ai_macro_sentinel/ai_regime.
    """
    try:
        ind_json = json.dumps(indicators or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        ind_json = "{}"
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO rejected_checks
                    (ts, symbol, filter, detail, indicators_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    str(symbol or "-"),
                    str(filter or "-"),
                    str(detail or ""),
                    ind_json,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать отклонение проверки: {exc}")


def get_recent_errors(limit: int = 5) -> list[dict[str, Any]]:
    """Последние `limit` убыточных сделок (outcome='LOSS')."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, side, entry, exit, qty, pnl, ema, rsi,
                       atr, ai_reason, outcome, closed_ts
                FROM trades
                WHERE outcome = 'LOSS'
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения последних ошибок: {exc}")
        return []


def get_last_rejection() -> Optional[dict[str, Any]]:
    """Последний отклонённый ИИ сигнал из старой таблицы rejected_signals."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT id, ts, reason, confidence, context_json
                FROM rejected_signals
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["context"] = json.loads(data.pop("context_json") or "{}")
            except json.JSONDecodeError:
                data["context"] = {}
            return data
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения последнего отклонения: {exc}")
        return None


def get_recent_rejected_checks(limit: int = 20) -> list[dict[str, Any]]:
    """Кольцевой буфер последних детерминированных отклонений v2."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, filter, detail, indicators_json
                FROM rejected_checks
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                data = dict(r)
                try:
                    data["indicators"] = json.loads(
                        data.pop("indicators_json") or "{}"
                    )
                except json.JSONDecodeError:
                    data["indicators"] = {}
                out.append(data)
            return out
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения rejected_checks: {exc}")
        return []


def get_last_rejected_check() -> Optional[dict[str, Any]]:
    """Последнее детерминированное отклонение v2 (для кнопки «ПОЧЕМУ МИМО?»)."""
    rows = get_recent_rejected_checks(limit=1)
    return rows[0] if rows else None


def get_open_trades() -> list[dict[str, Any]]:
    """Список сделок со статусом OPEN (для кнопки ПОЗИЦИИ в Telegram)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason
                FROM trades
                WHERE outcome = 'OPEN'
                ORDER BY id DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения открытых сделок: {exc}")
        return []


def get_stats() -> dict[str, Any]:
    """Сводная статистика: count, wins, losses, winrate, pnl_sum."""
    stats = {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
        "pnl_sum": 0.0,
    }
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                       AS count,
                    SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
                    COALESCE(SUM(pnl), 0)                          AS pnl_sum
                FROM trades
                WHERE outcome IN ('WIN','LOSS')
                """
            ).fetchone()
            if row is not None:
                count = int(row["count"] or 0)
                wins = int(row["wins"] or 0)
                losses = int(row["losses"] or 0)
                stats["count"] = count
                stats["wins"] = wins
                stats["losses"] = losses
                stats["pnl_sum"] = float(row["pnl_sum"] or 0.0)
                total = wins + losses
                stats["winrate"] = (wins / total * 100.0) if total else 0.0
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения статистики: {exc}")
    return stats


def get_trades_count_window_hours(hours: int) -> int:
    """Кол-во сделок (открытых и закрытых), попавших в окно `hours` часов.

    Считаются записи trades, у которых datetime(COALESCE(closed_ts, ts))
    попадает в последние `hours` часов от текущего момента. Используется
    для прогресс-бара дневного лимита сделок в карточке СТАТУС. Возвращает
    0 при ошибке БД.
    """
    try:
        h = int(hours)
    except (TypeError, ValueError):
        return 0
    if h <= 0:
        return 0
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM trades
                WHERE datetime(COALESCE(closed_ts, ts))
                      >= datetime('now', ?)
                """,
                (f"-{h} hours",),
            ).fetchone()
            if row is None:
                return 0
            return int(row["c"] or 0)
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения trades_count_window_hours: {exc}")
        return 0


def get_winrate_window_hours(hours: int) -> dict[str, Any]:
    """Винрейт за окно `hours` часов (по closed_ts закрытых сделок).

    Шаблон совпадает с get_stats(), но добавлен фильтр окна по closed_ts
    и считаются только сделки с outcome IN ('WIN','LOSS'). Возвращает
    словарь { 'count', 'wins', 'losses', 'winrate' } (winrate в процентах).
    """
    out: dict[str, Any] = {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
    }
    try:
        h = int(hours)
    except (TypeError, ValueError):
        return out
    if h <= 0:
        return out
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                       AS count,
                    SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses
                FROM trades
                WHERE outcome IN ('WIN','LOSS')
                  AND datetime(closed_ts) >= datetime('now', ?)
                """,
                (f"-{h} hours",),
            ).fetchone()
            if row is not None:
                count = int(row["count"] or 0)
                wins = int(row["wins"] or 0)
                losses = int(row["losses"] or 0)
                out["count"] = count
                out["wins"] = wins
                out["losses"] = losses
                total = wins + losses
                out["winrate"] = (wins / total * 100.0) if total else 0.0
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения winrate_window_hours: {exc}")
    return out


# --- v2: equity_curve и PnL-срезы ---

def record_equity(equity: float, hwm: float, drawdown: float) -> None:
    """Записать снимок эквити, HWM и текущей просадки."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO equity_curve (ts, equity, hwm, drawdown)
                VALUES (?, ?, ?, ?)
                """,
                (_now_iso(), float(equity), float(hwm), float(drawdown)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать equity-снимок: {exc}")


def get_equity_curve(days: int) -> list[dict[str, Any]]:
    """Все снимки эквити за последние `days` суток, от старых к новым."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, equity, hwm, drawdown
                FROM equity_curve
                WHERE datetime(ts) >= datetime('now', ?)
                ORDER BY id ASC
                """,
                (f"-{int(days)} days",),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения equity_curve: {exc}")
        return []


def get_hwm() -> float:
    """Наибольший HWM за всё время (или 0.0 если пусто)."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(hwm), 0.0) AS v FROM equity_curve"
            ).fetchone()
            return float(row["v"] if row else 0.0)
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения HWM: {exc}")
        return 0.0


def get_current_drawdown() -> float:
    """Просадка последнего снимка (или 0.0 если пусто)."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT drawdown
                FROM equity_curve
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            return float(row["drawdown"]) if row else 0.0
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения текущей просадки: {exc}")
        return 0.0


def get_trades_since(days: int) -> list[dict[str, Any]]:
    """Все сделки (любой outcome) за последние `days` суток, от старых к новым."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, side, entry, exit, qty, pnl, ema, rsi,
                       atr, ai_reason, outcome, closed_ts
                FROM trades
                WHERE datetime(ts) >= datetime('now', ?)
                ORDER BY id ASC
                """,
                (f"-{int(days)} days",),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения get_trades_since: {exc}")
        return []


def get_week_pnl() -> float:
    """Сумма pnl по сделкам, закрытым за последние 7 суток."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(pnl), 0.0) AS v
                FROM trades
                WHERE closed_ts IS NOT NULL
                  AND datetime(closed_ts) >= datetime('now', '-7 days')
                """
            ).fetchone()
            return float(row["v"] if row else 0.0)
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка расчёта недельного PnL: {exc}")
        return 0.0


# --- v3: AI-veto gate log и аггрегации ---

def record_ai_gate(
    symbol: str,
    side: str,
    strategy: Optional[str],
    verdict: str,
    reason: Optional[str],
    confidence: Optional[int],
    applied: bool,
) -> None:
    """Записать решение AI-veto gate для конкретного намерения открыть сделку.

    applied=True означает, что решение было фактически применено к торговле
    (актуально только для active-режима при verdict in (veto, error)).
    В shadow-режиме applied всегда False - решение только логируется.
    """
    try:
        conf_int = int(confidence) if confidence is not None else 0
    except (TypeError, ValueError):
        conf_int = 0
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_gate_log
                    (ts, symbol, side, strategy, verdict, reason,
                     confidence, applied)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    str(symbol or "-"),
                    str(side or "-"),
                    str(strategy or "") or None,
                    str(verdict or "-"),
                    str(reason or "") or None,
                    conf_int,
                    1 if applied else 0,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать решение AI-gate: {exc}")


def get_ai_gate_stats(hours: int) -> dict[str, int]:
    """Аггрегированная статистика по ai_gate_log за последние `hours` часов.

    Возвращает dict с ключами: approve, veto, error, total, applied.
    """
    out = {"approve": 0, "veto": 0, "error": 0, "total": 0, "applied": 0}
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT verdict, COUNT(*) AS cnt,
                       SUM(CASE WHEN applied=1 THEN 1 ELSE 0 END) AS applied_cnt
                FROM ai_gate_log
                WHERE datetime(ts) >= datetime('now', ?)
                GROUP BY verdict
                """,
                (f"-{int(hours)} hours",),
            ).fetchall()
            for r in rows:
                verdict = str(r["verdict"] or "").lower()
                cnt = int(r["cnt"] or 0)
                applied_cnt = int(r["applied_cnt"] or 0)
                if verdict in out:
                    out[verdict] = cnt
                out["total"] += cnt
                out["applied"] += applied_cnt
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_ai_gate_stats: {exc}")
    return out


def get_ai_gate_top_veto_reasons(
    hours: int, limit: int = 5
) -> list[dict[str, Any]]:
    """Топ причин veto/error за последние `hours` часов, по убыванию count.

    Возвращает список [{"reason": str, "count": int}, ...] длиной до `limit`.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(reason, '(без причины)') AS reason,
                       COUNT(*) AS cnt
                FROM ai_gate_log
                WHERE verdict IN ('veto', 'error')
                  AND datetime(ts) >= datetime('now', ?)
                GROUP BY reason
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (f"-{int(hours)} hours", int(limit)),
            ).fetchall()
            return [{"reason": str(r["reason"]), "count": int(r["cnt"] or 0)}
                    for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_ai_gate_top_veto_reasons: {exc}")
        return []


def get_ai_gate_recent(limit: int = 20) -> list[dict[str, Any]]:
    """Последние `limit` решений gate в порядке от новых к старым."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, side, strategy, verdict, reason,
                       confidence, applied
                FROM ai_gate_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                data = dict(r)
                data["applied"] = bool(data.get("applied"))
                out.append(data)
            return out
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_ai_gate_recent: {exc}")
        return []


def get_rejected_counts(hours: int) -> list[dict[str, Any]]:
    """Группировка rejected_checks по полю filter за последние `hours` часов.

    Возвращает список [{"filter": str, "count": int}, ...],
    отсортированный по убыванию count.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT filter, COUNT(*) AS cnt
                FROM rejected_checks
                WHERE datetime(ts) >= datetime('now', ?)
                GROUP BY filter
                ORDER BY cnt DESC
                """,
                (f"-{int(hours)} hours",),
            ).fetchall()
            return [{"filter": str(r["filter"]), "count": int(r["cnt"] or 0)}
                    for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_rejected_counts: {exc}")
        return []


# --- v3: symbol_blocks (запретный список manual + auto) ------------------

def add_symbol_block(
    symbol: str,
    type: str,  # noqa: A002 - совпадает с именем колонки
    until_iso: Optional[str],
    reason: Optional[str] = None,
) -> Optional[int]:
    """Создать новую запись в запретном списке.

    type: 'manual' | 'auto'.
    until_iso: ISO-время истечения блока (UTC, например '2099-01-01T00:00:00+00:00').
        None = бессрочный блок (только до ручного снятия).
    Возвращает id созданной записи или None при ошибке.
    """
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO symbol_blocks
                    (symbol, type, until_iso, reason, added_iso)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(symbol or "-").strip().upper(),
                    str(type or "manual"),
                    str(until_iso) if until_iso else None,
                    str(reason) if reason else None,
                    _now_iso(),
                ),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось добавить symbol_block({symbol}): {exc}")
        return None


def remove_symbol_block(
    symbol: str,
    type: Optional[str] = None,  # noqa: A002
) -> int:
    """Удалить блоки по символу. Если type=None - удаляет любые активные
    блоки (как manual, так и auto). Возвращает число удалённых записей."""
    try:
        sym = str(symbol or "-").strip().upper()
        with _connect() as conn:
            if type is None:
                cur = conn.execute(
                    "DELETE FROM symbol_blocks WHERE symbol = ?",
                    (sym,),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM symbol_blocks WHERE symbol = ? AND type = ?",
                    (sym, str(type)),
                )
            conn.commit()
            return int(cur.rowcount or 0)
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось удалить symbol_block({symbol}): {exc}")
        return 0


def list_active_blocks() -> list[dict[str, Any]]:
    """Все активные (не истёкшие) блоки. Возвращает list[dict] с полями
    id, symbol, type, until_iso, reason, added_iso. Сортировка - сначала
    свежие added_iso."""
    now = _now_iso()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, type, until_iso, reason, added_iso
                FROM symbol_blocks
                WHERE until_iso IS NULL OR until_iso > ?
                ORDER BY added_iso DESC, id DESC
                """,
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка list_active_blocks: {exc}")
        return []


def is_symbol_blocked(
    symbol: str,
) -> tuple[bool, Optional[dict[str, Any]]]:
    """Проверка наличия активного блока на символ.

    Сначала ищет manual (приоритет выше — пользователь явно запретил),
    потом auto. Возвращает (True, row) при первом найденном активном блоке;
    иначе (False, None). Истёкшие блоки автоматически отфильтровываются.
    """
    sym = str(symbol or "-").strip().upper()
    now = _now_iso()
    try:
        with _connect() as conn:
            # Сначала manual.
            row = conn.execute(
                """
                SELECT id, symbol, type, until_iso, reason, added_iso
                FROM symbol_blocks
                WHERE symbol = ? AND type = 'manual'
                  AND (until_iso IS NULL OR until_iso > ?)
                ORDER BY added_iso DESC, id DESC
                LIMIT 1
                """,
                (sym, now),
            ).fetchone()
            if row:
                return True, dict(row)
            # Потом auto.
            row = conn.execute(
                """
                SELECT id, symbol, type, until_iso, reason, added_iso
                FROM symbol_blocks
                WHERE symbol = ? AND type = 'auto'
                  AND (until_iso IS NULL OR until_iso > ?)
                ORDER BY added_iso DESC, id DESC
                LIMIT 1
                """,
                (sym, now),
            ).fetchone()
            if row:
                return True, dict(row)
            return False, None
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка is_symbol_blocked({symbol}): {exc}")
        return False, None


def get_symbol_stats_30d(symbol: str) -> dict[str, Any]:
    """Сводная статистика по конкретному символу за последние 30 суток.

    Возвращает dict с ключами:
        count, wins, losses, winrate, pnl_sum, avg_pnl, avg_rr_realized.

    Учитываются только закрытые сделки (outcome IN ('WIN','LOSS') и
    closed_ts IS NOT NULL). avg_rr_realized оставлен 0.0 — расчёт R по
    риску требует знать risk_per_trade на момент открытия (сейчас в схеме
    trades такой колонки нет, поэтому подменить нечем). Поле оставлено
    в сигнатуре чтобы не ломать вызывающий код, когда расчёт появится.
    """
    stats: dict[str, Any] = {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
        "pnl_sum": 0.0,
        "avg_pnl": 0.0,
        "avg_rr_realized": 0.0,
    }
    sym = str(symbol or "-").strip().upper()
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                       AS count,
                    SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
                    COALESCE(SUM(pnl), 0.0)                        AS pnl_sum,
                    COALESCE(AVG(pnl), 0.0)                        AS avg_pnl
                FROM trades
                WHERE symbol = ?
                  AND outcome IN ('WIN','LOSS')
                  AND closed_ts IS NOT NULL
                  AND datetime(closed_ts) >= datetime('now', '-30 days')
                """,
                (sym,),
            ).fetchone()
            if row is not None:
                count = int(row["count"] or 0)
                wins = int(row["wins"] or 0)
                losses = int(row["losses"] or 0)
                stats["count"] = count
                stats["wins"] = wins
                stats["losses"] = losses
                stats["pnl_sum"] = float(row["pnl_sum"] or 0.0)
                stats["avg_pnl"] = float(row["avg_pnl"] or 0.0)
                total = wins + losses
                stats["winrate"] = (wins / total * 100.0) if total else 0.0
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_symbol_stats_30d({symbol}): {exc}")
    return stats


def get_last_trades(symbol: str, n: int = 3) -> list[dict[str, Any]]:
    """Последние n WIN/LOSS-сделок по символу, новейшие первыми.

    Возвращает список dict с полями {ts, side, pnl, outcome}. ts —
    closed_ts (момент закрытия), если он есть; иначе ts открытия.
    """
    sym = str(symbol or "-").strip().upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT ts, closed_ts, side, pnl, outcome
                FROM trades
                WHERE symbol = ?
                  AND outcome IN ('WIN','LOSS')
                  AND closed_ts IS NOT NULL
                ORDER BY closed_ts DESC, id DESC
                LIMIT ?
                """,
                (sym, int(n)),
            ).fetchall()
            return [
                {
                    "ts": r["closed_ts"] or r["ts"],
                    "side": str(r["side"] or "-"),
                    "pnl": float(r["pnl"] or 0.0),
                    "outcome": str(r["outcome"] or "-"),
                }
                for r in rows
            ]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_last_trades({symbol}): {exc}")
        return []


def get_top_loss_reasons(
    symbol: str, days: int = 30, limit: int = 3,
) -> list[dict[str, Any]]:
    """Топ-N filter из rejected_checks за `days` суток для конкретного
    символа: «какие фильтры чаще всего блокируют этот символ».

    Возвращает список [{"filter": str, "count": int}, ...] длиной до
    `limit`. На пустой выборке — пустой список.
    """
    sym = str(symbol or "-").strip().upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT filter, COUNT(*) AS cnt
                FROM rejected_checks
                WHERE symbol = ?
                  AND datetime(ts) >= datetime('now', ?)
                  AND filter NOT IN ('manual_block', 'auto_block_loss_streak')
                GROUP BY filter
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (sym, f"-{int(days)} days", int(limit)),
            ).fetchall()
            return [
                {"filter": str(r["filter"]), "count": int(r["cnt"] or 0)}
                for r in rows
            ]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_top_loss_reasons({symbol}): {exc}")
        return []


def get_per_symbol_stats(days: int = 30) -> list[dict[str, Any]]:
    """По каждому символу из config.SYMBOLS — сводка за `days` суток.

    Возвращает список dict с ключами {symbol, count, wins, losses,
    winrate, pnl_sum}, отсортированный по pnl_sum DESC. Сделки учитываются
    только закрытые (outcome IN ('WIN','LOSS') и closed_ts NOT NULL).

    Итог по всем символам считается отдельно вызывающей стороной (для UI).
    """
    try:
        import config as _cfg  # noqa: PLC0415
        symbols = list(getattr(_cfg, "SYMBOLS", []) or [])
    except Exception:  # noqa: BLE001
        symbols = []
    out: list[dict[str, Any]] = []
    try:
        with _connect() as conn:
            for sym in symbols:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*)                                       AS count,
                        SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
                        SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
                        COALESCE(SUM(pnl), 0.0)                        AS pnl_sum
                    FROM trades
                    WHERE symbol = ?
                      AND outcome IN ('WIN','LOSS')
                      AND closed_ts IS NOT NULL
                      AND datetime(closed_ts) >= datetime('now', ?)
                    """,
                    (str(sym), f"-{int(days)} days"),
                ).fetchone()
                count = int(row["count"] or 0) if row else 0
                wins = int(row["wins"] or 0) if row else 0
                losses = int(row["losses"] or 0) if row else 0
                pnl_sum = float(row["pnl_sum"] or 0.0) if row else 0.0
                total = wins + losses
                winrate = (wins / total * 100.0) if total else 0.0
                out.append({
                    "symbol": str(sym),
                    "count": count,
                    "wins": wins,
                    "losses": losses,
                    "winrate": winrate,
                    "pnl_sum": pnl_sum,
                })
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_per_symbol_stats: {exc}")
        return []
    out.sort(key=lambda r: r["pnl_sum"], reverse=True)
    return out


def get_consecutive_losses(symbol: str, limit: int = 10) -> int:
    """Количество подряд идущих LOSS по символу с самой свежей закрытой
    сделки до первого не-LOSS (WIN или OPEN). Open-сделки игнорируются —
    учитываем только закрытые (closed_ts IS NOT NULL).

    Сортировка по closed_ts DESC. Лимит ограничивает максимально
    просматриваемое число записей (по умолчанию 10 — достаточно для
    AUTO_BLOCK_LOSS_STREAK уровня 2/3/5).
    """
    sym = str(symbol or "-").strip().upper()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT outcome
                FROM trades
                WHERE symbol = ?
                  AND closed_ts IS NOT NULL
                  AND outcome IN ('WIN', 'LOSS')
                ORDER BY closed_ts DESC, id DESC
                LIMIT ?
                """,
                (sym, int(limit)),
            ).fetchall()
            streak = 0
            for r in rows:
                if str(r["outcome"] or "").upper() == "LOSS":
                    streak += 1
                else:
                    break
            return streak
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка get_consecutive_losses({symbol}): {exc}")
        return 0


# Инициализация схемы выполняется явно из main.py::main() через
# memory.init_db(). Авто-вызов при импорте убран, чтобы:
#   1) не печатать "[MEMORY] ... инициализирована" дважды (main + import);
#   2) не создавать побочных эффектов при тестовом/утилитарном импорте.
# Потребители (telegram_bot, backtester и т.п.) к БД обращаются уже после
# старта main(), поэтому порядок инициализации сохраняется.
