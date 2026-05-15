"""WhatsApp адаптер для мультиплатформенной поддержки (заглушка)."""

import logging
from typing import Optional, Dict, Any

from platform_adapter import PlatformAdapter

logger = logging.getLogger(__name__)


class WhatsAppAdapter(PlatformAdapter):
    """
    Адаптер для WhatsApp Business API.

    TODO: Реализовать интеграцию с WhatsApp Business API.
    Требуется: Meta Business Account, WhatsApp Business API token.
    """

    def __init__(self, api_token: Optional[str] = None, phone_number_id: Optional[str] = None):
        """
        Инициализация WhatsApp адаптера.

        Args:
            api_token: токен WhatsApp Business API
            phone_number_id: ID номера телефона
        """
        self._api_token = api_token
        self._phone_number_id = phone_number_id

    @property
    def platform_name(self) -> str:
        """Название платформы."""
        return "whatsapp"

    async def send_message(
        self, user_id: int, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """Отправить сообщение через WhatsApp. TODO: реализовать."""
        raise NotImplementedError("WhatsApp adapter not yet implemented")

    async def send_document(
        self, user_id: int, file_path: str, caption: Optional[str] = None
    ) -> bool:
        """Отправить документ через WhatsApp. TODO: реализовать."""
        raise NotImplementedError("WhatsApp adapter not yet implemented")

    async def send_photo(
        self, user_id: int, photo_path: str, caption: Optional[str] = None
    ) -> bool:
        """Отправить фото через WhatsApp. TODO: реализовать."""
        raise NotImplementedError("WhatsApp adapter not yet implemented")

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе WhatsApp. TODO: реализовать."""
        raise NotImplementedError("WhatsApp adapter not yet implemented")
