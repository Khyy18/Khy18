"""Публикация постов в Telegram-канал с rate limiting."""

import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

logger = logging.getLogger(__name__)

# Ограничение: не более 20 сообщений в минуту
_MAX_MESSAGES_PER_MINUTE = 20
_SEMAPHORE = asyncio.Semaphore(_MAX_MESSAGES_PER_MINUTE)
_MAX_RETRIES = 3


class ChannelPublisher:
    """Публикация постов в Telegram-канал с контролем rate limit."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._last_sent: float = 0.0
        self._min_interval = 60.0 / _MAX_MESSAGES_PER_MINUTE  # секунд между сообщениями

    async def publish_to_channel(
        self,
        channel_id: str | int,
        post_text: str,
        product_url: str | None = None,
    ) -> int:
        """Опубликовать пост в канал.

        Args:
            channel_id: ID канала или @username.
            post_text: HTML-текст поста.
            product_url: опциональная ссылка на товар (для inline-кнопки).

        Returns:
            message_id отправленного сообщения.
        """
        async with _SEMAPHORE:
            return await self._send_with_retry(channel_id, post_text, product_url)

    async def _send_with_retry(
        self,
        channel_id: str | int,
        post_text: str,
        product_url: str | None,
    ) -> int:
        """Отправка с ретраями при rate limit."""
        # Контроль минимального интервала между сообщениями
        now = time.time()
        elapsed = now - self._last_sent
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                msg = await self._bot.send_message(
                    chat_id=channel_id,
                    text=post_text,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
                self._last_sent = time.time()
                logger.info("Пост опубликован в канал %s (msg_id=%d)", channel_id, msg.message_id)
                return msg.message_id
            except TelegramRetryAfter as e:
                wait_time = e.retry_after
                logger.warning(
                    "Rate limit, ждём %d сек (попытка %d/%d)",
                    wait_time,
                    attempt,
                    _MAX_RETRIES,
                )
                await asyncio.sleep(wait_time)
            except Exception as e:
                if attempt == _MAX_RETRIES:
                    logger.error("Не удалось опубликовать пост после %d попыток: %s", _MAX_RETRIES, e)
                    raise
                # Экспоненциальная задержка
                backoff = 2 ** attempt
                logger.warning("Ошибка отправки (попытка %d/%d): %s. Ждём %d сек", attempt, _MAX_RETRIES, e, backoff)
                await asyncio.sleep(backoff)

        # Этот return формально недостижим, но нужен для типизации
        raise RuntimeError("Не удалось отправить сообщение")
