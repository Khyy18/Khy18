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

Этот модуль - тонкая обёртка поверх db.sqlite_backend.SQLiteBackend.
Все публичные функции делегируют вызовы в инстанс _storage.
Обратная совместимость сохранена: все сигнатуры и поведение идентичны.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional

from db.sqlite_backend import SQLiteBackend


# Путь к SQLite trades.db.
# Приоритет: TRADES_DB_PATH (env) -> /app/data/trades.db если такой каталог
# смонтирован (persistent volume на Fly.io/Docker) -> рядом с memory.py
# (локальный запуск).
def _resolve_db_path() -> str:
    env_path = os.getenv("TRADES_DB_PATH", "").strip()
    if env_path:
        return env_path
    persistent_dir = "/app/data"
    if os.path.isdir(persistent_dir) and os.access(persistent_dir, os.W_OK):
        return os.path.join(persistent_dir, "trades.db")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")


DB_PATH = _resolve_db_path()

# Инстанс хранилища - делегат для всех функций модуля.
_storage = SQLiteBackend(db_path=DB_PATH)


def _connect() -> sqlite3.Connection:
    """Для обратной совместимости с кодом, напрямую вызывающим _connect()."""
    return _storage._connect()


def init_db() -> None:
    """Создать таблицы и применить лёгкие миграции. Идемпотентно."""
    _storage.init_db()


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
    return _storage.record_trade(
        symbol=symbol,
        side=side,
        entry=entry,
        qty=qty,
        ema_val=ema_val,
        rsi_val=rsi_val,
        atr_val=atr_val,
        ai_reason=ai_reason,
        outcome=outcome,
    )


def update_trade_outcome(
    trade_id: int,
    exit_price: float,
    pnl: float,
    outcome: str,
) -> None:
    """Обновить результат сделки (WIN/LOSS/OPEN). Ставит closed_ts = сейчас."""
    _storage.update_trade_outcome(
        trade_id=trade_id,
        exit_price=exit_price,
        pnl=pnl,
        outcome=outcome,
    )


def record_rejection(
    reason: str,
    confidence: int,
    ctx: dict[str, Any],
) -> None:
    """Сохранить отклонённый сигнал (старая v1-таблица)."""
    _storage.record_rejection(reason=reason, confidence=confidence, ctx=ctx)


def record_rejected_check(
    symbol: str,
    filter: str,  # noqa: A002
    detail: str,
    indicators: Optional[dict[str, Any]] = None,
) -> None:
    """v2: запись детерминированного отклонения (Donchian, blackout, режим)."""
    _storage.record_rejected_check(
        symbol=symbol, filter=filter, detail=detail, indicators=indicators
    )


def get_recent_errors(limit: int = 5) -> list[dict[str, Any]]:
    """Последние `limit` убыточных сделок (outcome='LOSS')."""
    return _storage.get_recent_errors(limit=limit)


def get_last_rejection() -> Optional[dict[str, Any]]:
    """Последний отклонённый ИИ сигнал из старой таблицы rejected_signals."""
    return _storage.get_last_rejection()


def get_recent_rejected_checks(limit: int = 20) -> list[dict[str, Any]]:
    """Кольцевой буфер последних детерминированных отклонений v2."""
    return _storage.get_recent_rejected_checks(limit=limit)


def get_last_rejected_check() -> Optional[dict[str, Any]]:
    """Последнее детерминированное отклонение v2 (для кнопки 'ПОЧЕМУ МИМО?')."""
    return _storage.get_last_rejected_check()


def get_open_trades() -> list[dict[str, Any]]:
    """Список сделок со статусом OPEN (для кнопки ПОЗИЦИИ в Telegram)."""
    return _storage.get_open_trades()


def get_stats() -> dict[str, Any]:
    """Сводная статистика: count, wins, losses, winrate, pnl_sum."""
    return _storage.get_stats()


# --- v2: equity_curve и PnL-срезы ---

def record_equity(equity: float, hwm: float, drawdown: float) -> None:
    """Записать снимок эквити, HWM и текущей просадки."""
    _storage.record_equity(equity=equity, hwm=hwm, drawdown=drawdown)


def get_equity_curve(days: int) -> list[dict[str, Any]]:
    """Все снимки эквити за последние `days` суток, от старых к новым."""
    return _storage.get_equity_curve(days=days)


def get_hwm() -> float:
    """Наибольший HWM за всё время (или 0.0 если пусто)."""
    return _storage.get_hwm()


def get_current_drawdown() -> float:
    """Просадка последнего снимка (или 0.0 если пусто)."""
    return _storage.get_current_drawdown()


def get_trades_since(days: int) -> list[dict[str, Any]]:
    """Все сделки (любой outcome) за последние `days` суток, от старых к новым."""
    return _storage.get_trades_since(days=days)


def get_week_pnl() -> float:
    """Сумма pnl по сделкам, закрытым за последние 7 суток."""
    return _storage.get_week_pnl()


# --- KV-store -----------------------------------------------------------

def kv_set(key: str, value: Any) -> None:
    """Записать произвольное JSON-сериализуемое значение в kv_store."""
    _storage.kv_set(key=key, value=value)


def kv_get(key: str, default: Any = None) -> Any:
    """Прочитать значение из kv_store. На любой ошибке возвращает default."""
    return _storage.kv_get(key=key, default=default)
