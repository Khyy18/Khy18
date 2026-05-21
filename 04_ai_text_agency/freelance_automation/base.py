"""Базовый класс и модели для фриланс-платформ."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Order:
    """Заказ на фриланс-площадке."""

    id: str
    title: str
    description: str
    budget: Optional[float]
    url: str
    category: Optional[str] = None
    posted_at: Optional[datetime] = None


class FreelancePlatform(ABC):
    """Абстрактный базовый класс для фриланс-платформы."""

    # Опциональная конфигурация антидетекта (StealthConfig)
    stealth_config = None

    @abstractmethod
    async def login(self, cookies_path: str) -> bool:
        """Авторизация через cookies."""
        ...

    @abstractmethod
    async def fetch_new_orders(
        self,
        keywords: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> list[Order]:
        """Получение новых заказов, опционально фильтруя по ключевым словам или категориям."""
        ...

    @abstractmethod
    async def respond_to_order(self, order: Order, text: str, use_ai: bool = False) -> bool:
        """Отправка отклика на заказ."""
        ...

    @abstractmethod
    async def check_order_status(self, order: Order) -> str:
        """Проверка статуса заказа: 'pending', 'accepted', 'completed', 'rejected'."""
        ...

    @abstractmethod
    async def deliver_order(self, order: Order, completion_text: str) -> bool:
        """Отправка готового результата клиенту после принятия заказа."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Закрытие браузера и освобождение ресурсов."""
        ...
