"""Telegram-обработчики для Lead Scoring.

Команды: /leads, /lead_threshold
"""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from lead_scoring.models import get_top_leads, init_db
from logging_config import get_logger

log = get_logger(__name__)


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def _send_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as e:
        log.error("telegram_send_error", error=str(e), chat_id=chat_id)
        return None


async def handle_leads_command(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Обработчик /leads - показать топ-10 лидов по оценке."""
    init_db()
    leads = get_top_leads(limit=10, min_score=0)

    if not leads:
        await _send_message(session, chat_id, "Нет оцененных лидов.")
        return

    lines = ["<b>Топ-10 лидов:</b>\n"]
    for i, lead in enumerate(leads, 1):
        lines.append(
            f"{i}. [Score: {lead['score']}] Order: {lead['order_id']}"
        )

    text = "\n".join(lines)
    await _send_message(session, chat_id, text)
    log.info("leads_command", chat_id=chat_id, count=len(leads))


async def handle_lead_threshold_command(
    session: aiohttp.ClientSession,
    chat_id: int,
    threshold: int,
) -> None:
    """Обработчик /lead_threshold - обновить порог авто-ответа."""
    threshold = max(0, min(100, threshold))
    config.LEAD_SCORE_AUTO_RESPOND_THRESHOLD = threshold

    text = f"Порог авто-ответа обновлен: <b>{threshold}</b>"
    await _send_message(session, chat_id, text)
    log.info("lead_threshold_updated", chat_id=chat_id, threshold=threshold)
