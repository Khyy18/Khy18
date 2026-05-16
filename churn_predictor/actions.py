"""Retention actions triggered by churn risk predictions."""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from logging_config import get_logger

log = get_logger(__name__)


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def _send_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
) -> Optional[dict[str, Any]]:
    """Send a message via Telegram Bot API."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as e:
        log.error("telegram_send_error", error=str(e), chat_id=chat_id)
        return None


class RetentionActions:
    """Takes retention actions based on churn risk."""

    async def take_action(
        self,
        session: aiohttp.ClientSession,
        tg_id: int,
        churn_risk: float,
    ) -> None:
        """Take action based on churn risk level.

        Args:
            session: aiohttp session
            tg_id: Telegram user ID
            churn_risk: probability of churn (0-1)
        """
        if churn_risk > 0.9:
            # Critical risk - alert admin and send discount
            await self._send_discount(session, tg_id)
            await self._alert_admin(session, tg_id, churn_risk)
            log.warning("churn_critical", tg_id=tg_id, risk=churn_risk)
        elif churn_risk > 0.7:
            # High risk - send personalized discount
            await self._send_discount(session, tg_id)
            log.info("churn_high_risk_discount_sent", tg_id=tg_id, risk=churn_risk)

    async def _send_discount(
        self, session: aiohttp.ClientSession, tg_id: int
    ) -> None:
        """Send a personalized discount message."""
        text = (
            "<b>Специальное предложение для вас!</b>\n\n"
            "Мы заметили, что вы давно не пользовались нашим сервисом. "
            "Используйте промокод <code>COMEBACK20</code> для скидки 20% "
            "на следующий заказ!\n\n"
            "Ждём вас обратно!"
        )
        await _send_message(session, tg_id, text)

    async def _alert_admin(
        self,
        session: aiohttp.ClientSession,
        tg_id: int,
        churn_risk: float,
    ) -> None:
        """Alert admin about critical churn risk."""
        if not config.TELEGRAM_CHAT_ID:
            return
        risk_pct = int(churn_risk * 100)
        text = (
            f"<b>Риск оттока клиента (критический):</b>\n"
            f"Клиент tg_id: {tg_id}\n"
            f"Вероятность: {risk_pct}%\n"
            f"Рекомендация: персональный контакт."
        )
        await _send_message(session, config.TELEGRAM_CHAT_ID, text)
