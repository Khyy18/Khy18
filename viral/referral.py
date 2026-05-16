"""Класс ReferralSystem - высокоуровневый интерфейс реферальной механики."""

from __future__ import annotations

from typing import Optional

from viral import models


class ReferralSystem:
    """Реферальная система с генерацией deep-link для Telegram-бота."""

    def __init__(self, bot_username: str) -> None:
        self.bot_username = bot_username
        models.init_db()

    def generate_link(self, tg_id: int) -> str:
        """Получить или создать реферальную ссылку для пользователя."""
        code = models.create_referral_code(tg_id)
        return f"https://t.me/{self.bot_username}?start=ref_{code}"

    def track_invitation(self, referral_code: str, new_user_tg_id: int) -> bool:
        """Зарегистрировать переход по реферальной ссылке."""
        return models.register_referral(referral_code, new_user_tg_id)

    def check_and_grant_bonus(self, paid_user_tg_id: int) -> Optional[dict]:
        """Начислить бонус рефереру при первой оплате приглашённого."""
        return models.grant_bonus_on_payment(paid_user_tg_id)

    def get_stats(self, tg_id: int) -> dict:
        """Получить статистику рефералов пользователя."""
        return models.get_referral_stats(tg_id)
