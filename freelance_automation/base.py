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
    async def fetch_new_orders(self, keywords: list[str] | None = None) -> list[Order]:
        """Получение новых заказов, опционально фильтруя по ключевым словам."""
        ...

    @abstractmethod
    async def respond_to_order(self, order: Order, text: str) -> bool:
        """Отправка отклика на заказ."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Закрытие браузера и освобождение ресурсов."""
        ...
