"""StorageProtocol - контракт для всех бэкендов хранилища."""

from __future__ import annotations

from typing import Any, Optional, Protocol


class StorageProtocol(Protocol):
    """Интерфейс хранилища торгового бота.

    Все методы синхронные для SQLite-бэкенда. Для async-бэкендов
    (PostgreSQL) используется отдельная обёртка.
    """

    def init_db(self) -> None:
        """Создать таблицы и применить миграции. Идемпотентно."""
        ...

    def record_trade(
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
        """Сохранить открытую сделку. Возвращает id."""
        ...

    def update_trade_outcome(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        outcome: str,
    ) -> None:
        """Обновить результат сделки (WIN/LOSS/OPEN)."""
        ...

    def record_rejection(
        self,
        reason: str,
        confidence: int,
        ctx: dict[str, Any],
    ) -> None:
        """Сохранить отклонённый сигнал (v1)."""
        ...

    def record_rejected_check(
        self,
        symbol: str,
        filter: str,
        detail: str,
        indicators: Optional[dict[str, Any]] = None,
    ) -> None:
        """Запись детерминированного отклонения (v2)."""
        ...

    def get_recent_errors(self, limit: int = 5) -> list[dict[str, Any]]:
        """Последние убыточные сделки (outcome='LOSS')."""
        ...

    def get_last_rejection(self) -> Optional[dict[str, Any]]:
        """Последний отклонённый ИИ сигнал (v1)."""
        ...

    def get_recent_rejected_checks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Последние детерминированные отклонения (v2)."""
        ...

    def get_last_rejected_check(self) -> Optional[dict[str, Any]]:
        """Последнее детерминированное отклонение (v2)."""
        ...

    def get_open_trades(self) -> list[dict[str, Any]]:
        """Список сделок со статусом OPEN."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Сводная статистика: count, wins, losses, winrate, pnl_sum."""
        ...

    def record_equity(self, equity: float, hwm: float, drawdown: float) -> None:
        """Записать снимок эквити, HWM и текущей просадки."""
        ...

    def get_equity_curve(self, days: int) -> list[dict[str, Any]]:
        """Снимки эквити за последние days суток."""
        ...

    def get_hwm(self) -> float:
        """Наибольший HWM за всё время."""
        ...

    def get_current_drawdown(self) -> float:
        """Просадка последнего снимка."""
        ...

    def get_trades_since(self, days: int) -> list[dict[str, Any]]:
        """Все сделки за последние days суток."""
        ...

    def get_week_pnl(self) -> float:
        """Сумма pnl за последние 7 суток."""
        ...

    def kv_set(self, key: str, value: Any) -> None:
        """Записать значение в kv_store."""
        ...

    def kv_get(self, key: str, default: Any = None) -> Any:
        """Прочитать значение из kv_store."""
        ...
