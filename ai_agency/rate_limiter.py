"""Rate limiter: защита от спама и злоупотреблений в боте."""

import logging
import time
from collections import defaultdict, deque
from typing import Tuple

logger = logging.getLogger(__name__)

# Лимиты
MAX_ORDERS_PER_HOUR = 5
FLOOD_MESSAGES_PER_MINUTE = 20
ORDER_COOLDOWN_SECONDS = 30


class RateLimiter:
    """
    Лимитирование запросов пользователей.

    Правила:
    - Макс. 5 заказов в час на пользователя
    - Бан при >20 сообщений в минуту (flood)
    - 30 секунд cooldown между заказами
    """

    def __init__(self):
        # user_id -> deque of timestamps (messages)
        self._messages: defaultdict = defaultdict(lambda: deque(maxlen=100))
        # user_id -> deque of timestamps (orders)
        self._orders: defaultdict = defaultdict(lambda: deque(maxlen=50))
        # user_id -> ban expiry timestamp
        self._bans: dict = {}

    def record_message(self, user_id: int) -> None:
        """Записать сообщение от пользователя."""
        self._messages[user_id].append(time.time())

    def record_order(self, user_id: int) -> None:
        """Записать заказ от пользователя."""
        self._orders[user_id].append(time.time())

    def is_banned(self, user_id: int) -> bool:
        """Проверить, забанен ли пользователь."""
        ban_until = self._bans.get(user_id)
        if ban_until is None:
            return False
        if time.time() >= ban_until:
            del self._bans[user_id]
            return False
        return True

    def get_cooldown_remaining(self, user_id: int) -> float:
        """Получить оставшееся время cooldown между заказами (секунды)."""
        orders = self._orders.get(user_id)
        if not orders:
            return 0.0
        last_order = orders[-1]
        elapsed = time.time() - last_order
        remaining = ORDER_COOLDOWN_SECONDS - elapsed
        return max(0.0, remaining)

    def _check_flood(self, user_id: int) -> bool:
        """Проверить, не флудит ли пользователь."""
        messages = self._messages.get(user_id)
        if not messages:
            return False
        minute_ago = time.time() - 60
        recent = sum(1 for t in messages if t > minute_ago)
        if recent > FLOOD_MESSAGES_PER_MINUTE:
            # Бан на 5 минут
            self._bans[user_id] = time.time() + 300
            logger.warning("Пользователь %d забанен за flood (%d msg/min)", user_id, recent)
            return True
        return False

    def _check_orders_limit(self, user_id: int) -> bool:
        """Проверить лимит заказов в час."""
        orders = self._orders.get(user_id)
        if not orders:
            return False
        hour_ago = time.time() - 3600
        recent = sum(1 for t in orders if t > hour_ago)
        return recent >= MAX_ORDERS_PER_HOUR

    def check_rate_limit(self, user_id: int) -> Tuple[bool, str]:
        """
        Проверить, может ли пользователь сделать заказ.

        Возвращает (allowed, message).
        allowed = True если заказ разрешён.
        """
        # Проверка бана
        if self.is_banned(user_id):
            ban_until = self._bans.get(user_id, 0)
            remaining = int(ban_until - time.time())
            return (False, f"Вы временно заблокированы. Подождите {remaining} сек.")

        # Проверка flood
        if self._check_flood(user_id):
            return (False, "Слишком много сообщений. Вы заблокированы на 5 минут.")

        # Проверка cooldown
        cooldown = self.get_cooldown_remaining(user_id)
        if cooldown > 0:
            return (False, f"Подождите {int(cooldown)} сек. перед следующим заказом.")

        # Проверка лимита заказов
        if self._check_orders_limit(user_id):
            return (False, "Превышен лимит: максимум 5 заказов в час.")

        return (True, "")
