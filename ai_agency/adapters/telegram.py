"""Telegram адаптер для мультиплатформенной поддержки."""

import logging
from typing import Optional, Dict, Any

from platform_adapter import PlatformAdapter

logger = logging.getLogger(__name__)

try:
    from telegram import Bot
except ImportError:
    Bot = None


class TelegramAdapter(PlatformAdapter):
    """Адаптер для Telegram, оборачивающий python-telegram-bot."""

    def __init__(self, bot=None, token: Optional[str] = None):
        """
        Инициализация Telegram адаптера.

        Args:
            bot: экземпляр telegram.Bot (если уже создан)
            token: токен бота (если bot не передан)
        """
        if bot is not None:
            self._bot = bot
        elif token and Bot is not None:
            self._bot = Bot(token=token)
        else:
            self._bot = None

    @property
    def platform_name(self) -> str:
        """Название платформы."""
        return "telegram"

    async def send_message(
        self, user_id: int, text: str, parse_mode: Optional[str] = None
    ) -> bool:
        """Отправить текстовое сообщение через Telegram."""
        if self._bot is None:
            logger.warning("Telegram bot не инициализирован")
            return False
        try:
            await self._bot.send_message(
                chat_id=user_id, text=text, parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.debug("Ошибка отправки Telegram сообщения %d: %s", user_id, e)
            return False

    async def send_document(
        self, user_id: int, file_path: str, caption: Optional[str] = None
    ) -> bool:
        """Отправить документ через Telegram."""
        if self._bot is None:
            return False
        try:
            with open(file_path, "rb") as f:
                await self._bot.send_document(
                    chat_id=user_id, document=f, caption=caption
                )
            return True
        except Exception as e:
            logger.debug("Ошибка отправки документа %d: %s", user_id, e)
            return False

    async def send_photo(
        self, user_id: int, photo_path: str, caption: Optional[str] = None
    ) -> bool:
        """Отправить фото через Telegram."""
        if self._bot is None:
            return False
        try:
            with open(photo_path, "rb") as f:
                await self._bot.send_photo(
                    chat_id=user_id, photo=f, caption=caption
                )
            return True
        except Exception as e:
            logger.debug("Ошибка отправки фото %d: %s", user_id, e)
            return False

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе Telegram."""
        if self._bot is None:
            return None
        try:
            chat = await self._bot.get_chat(chat_id=user_id)
            return {
                "id": chat.id,
                "username": chat.username,
                "first_name": chat.first_name,
                "last_name": chat.last_name,
                "platform": "telegram",
            }
        except Exception as e:
            logger.debug("Ошибка получения user_info %d: %s", user_id, e)
            return None
