"""Абстрактный адаптер платформ для мультиплатформенной поддержки."""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """Абстрактный базовый класс адаптера платформы."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Название платформы."""
        ...

    @abstractmethod
    async def send_message(
        self, user_id: int, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """
        Отправить текстовое сообщение пользователю.

        Args:
            user_id: ID пользователя на платформе
            text: текст сообщения
            parse_mode: режим парсинга (HTML, Markdown, etc.)

        Returns:
            True если отправлено успешно
        """
        ...

    @abstractmethod
    async def send_document(
        self, user_id: int, file_path: str, caption: Optional[str] = None
    ) -> bool:
        """
        Отправить документ пользователю.

        Args:
            user_id: ID пользователя
            file_path: путь к файлу
            caption: подпись к файлу

        Returns:
            True если отправлено успешно
        """
        ...

    @abstractmethod
    async def send_photo(
        self, user_id: int, photo_path: str, caption: Optional[str] = None
    ) -> bool:
        """
        Отправить фото пользователю.

        Args:
            user_id: ID пользователя
            photo_path: путь к фото
            caption: подпись

        Returns:
            True если отправлено успешно
        """
        ...

    @abstractmethod
    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о пользователе.

        Args:
            user_id: ID пользователя

        Returns:
            Dict с информацией или None
        """
        ...


class PlatformRouter:
    """Роутер для определения платформы и маршрутизации сообщений."""

    def __init__(self):
        """Инициализация роутера с пустым реестром адаптеров."""
        self._adapters: Dict[str, PlatformAdapter] = {}

    def register(self, adapter: PlatformAdapter) -> None:
        """Зарегистрировать адаптер платформы."""
        self._adapters[adapter.platform_name] = adapter
        logger.info("Зарегистрирован адаптер: %s", adapter.platform_name)

    def get_adapter(self, platform: str) -> Optional[PlatformAdapter]:
        """Получить адаптер по имени платформы."""
        return self._adapters.get(platform)

    @property
    def available_platforms(self) -> list:
        """Список доступных платформ."""
        return list(self._adapters.keys())

    async def send_message(
        self, platform: str, user_id: int, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """Отправить сообщение через соответствующий адаптер."""
        adapter = self.get_adapter(platform)
        if adapter is None:
            logger.warning("Адаптер для платформы %s не найден", platform)
            return False
        return await adapter.send_message(user_id, text, parse_mode)

    async def broadcast(
        self, user_ids: Dict[str, list], text: str, parse_mode: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Рассылка по всем платформам.

        Args:
            user_ids: dict {platform: [user_id, ...]}
            text: текст сообщения
            parse_mode: режим парсинга

        Returns:
            dict {platform: sent_count}
        """
        results = {}
        for platform, ids in user_ids.items():
            adapter = self.get_adapter(platform)
            if adapter is None:
                results[platform] = 0
                continue
            sent = 0
            for uid in ids:
                try:
                    if await adapter.send_message(uid, text, parse_mode):
                        sent += 1
                except Exception as e:
                    logger.debug("Ошибка отправки %s/%d: %s", platform, uid, e)
            results[platform] = sent
        return results
