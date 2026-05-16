"""Оркестратор мульти-аккаунтов - управление пулом аккаунтов у букмекеров.

Управляет балансами, лимитами и кулдаунами нескольких аккаунтов
для оптимального распределения ставок.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from arbitrage import memory

logger = logging.getLogger(__name__)


@dataclass
class Account:
    """Аккаунт в пуле."""

    id: int
    bookmaker: str
    account_name: str
    balance: float
    daily_limit: float
    daily_used: float
    status: str  # active, cooldown, limited, banned
    last_bet_ts: Optional[str]
    cooldown_until: Optional[str]


class MultiAccountOrchestrator:
    """Управление пулом аккаунтов у одного или нескольких букмекеров."""

    def select_account(self, bookmaker: str, stake: float) -> Optional[Account]:
        """Выбрать лучший аккаунт для ставки (баланс, лимит, кулдаун).

        Критерии выбора:
        1. Статус = active
        2. Не в кулдауне
        3. Достаточный баланс
        4. Не превышен дневной лимит
        5. Приоритет: больший остаток дневного лимита
        """
        accounts = memory.get_pool_accounts(bookmaker=bookmaker)
        now = datetime.now(tz=timezone.utc)

        candidates: list[Account] = []

        for row in accounts:
            acc = Account(
                id=row["id"],
                bookmaker=row["bookmaker"],
                account_name=row["account_name"],
                balance=row["balance"],
                daily_limit=row["daily_limit"],
                daily_used=row["daily_used"],
                status=row["status"],
                last_bet_ts=row.get("last_bet_ts"),
                cooldown_until=row.get("cooldown_until"),
            )

            # Пропускаем неактивные
            if acc.status != "active":
                continue

            # Проверяем кулдаун
            if acc.cooldown_until:
                try:
                    cooldown_dt = datetime.fromisoformat(acc.cooldown_until)
                    if cooldown_dt.tzinfo is None:
                        cooldown_dt = cooldown_dt.replace(tzinfo=timezone.utc)
                    if now < cooldown_dt:
                        continue
                except (ValueError, TypeError):
                    pass

            # Проверяем баланс
            if acc.balance < stake:
                continue

            # Проверяем дневной лимит
            remaining = acc.daily_limit - acc.daily_used
            if remaining < stake:
                continue

            candidates.append(acc)

        if not candidates:
            logger.info("[MULTI_ACC] Нет доступных аккаунтов для %s, ставка %.2f", bookmaker, stake)
            return None

        # Выбираем аккаунт с наибольшим остатком дневного лимита
        best = max(candidates, key=lambda a: a.daily_limit - a.daily_used)
        logger.info(
            "[MULTI_ACC] Выбран аккаунт %s @ %s (баланс: %.2f, лимит остаток: %.2f)",
            best.account_name,
            best.bookmaker,
            best.balance,
            best.daily_limit - best.daily_used,
        )
        return best

    def record_bet_on_account(self, account_id: int, stake: float) -> None:
        """Записать ставку на аккаунт (обновить daily_used и last_bet_ts)."""
        memory.update_pool_account_bet(account_id, stake)
        logger.info("[MULTI_ACC] Записана ставка %.2f на аккаунт #%d", stake, account_id)

    def get_accounts_status(self) -> list[Account]:
        """Получить все аккаунты с текущим статусом."""
        accounts = memory.get_pool_accounts()
        result: list[Account] = []
        for row in accounts:
            acc = Account(
                id=row["id"],
                bookmaker=row["bookmaker"],
                account_name=row["account_name"],
                balance=row["balance"],
                daily_limit=row["daily_limit"],
                daily_used=row["daily_used"],
                status=row["status"],
                last_bet_ts=row.get("last_bet_ts"),
                cooldown_until=row.get("cooldown_until"),
            )
            result.append(acc)
        return result
