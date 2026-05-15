"""VK (ВКонтакте) адаптер для мультиплатформенной поддержки (заглушка)."""

import logging
from typing import Optional, Dict, Any

from platform_adapter import PlatformAdapter

logger = logging.getLogger(__name__)


class VKAdapter(PlatformAdapter):
    """
    Адаптер для VK Bot API.

    TODO: Реализовать интеграцию с VK Bot API.
    Требуется: VK Community token, Group ID.
    """

    def __init__(self, token: Optional[str] = None, group_id: Optional[int] = None):
        """
        Инициализация VK адаптера.

        Args:
            token: токен сообщества VK
            group_id: ID группы VK
        """
        self._token = token
        self._group_id = group_id

    @property
    def platform_name(self) -> str:
        """Название платформы."""
        return "vk"

    async def send_message(
        self, user_id: int, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """Отправить сообщение через VK. TODO: реализовать."""
        raise NotImplementedError("VK adapter not yet implemented")

    async def send_document(
        self, user_id: int, file_path: str, caption: Optional[str] = None
    ) -> bool:
        """Отправить документ через VK. TODO: реализовать."""
        raise NotImplementedError("VK adapter not yet implemented")

    async def send_photo(
        self, user_id: int, photo_path: str, caption: Optional[str] = None
    ) -> bool:
        """Отправить фото через VK. TODO: реализовать."""
        raise NotImplementedError("VK adapter not yet implemented")

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе VK. TODO: реализовать."""
        raise NotImplementedError("VK adapter not yet implemented")
