"""Telegram-обработчики для CRM-модуля.

Команды:
  /clients - список клиентов по этапам воронки.
  /funnel  - статистика воронки (текстовая диаграмма).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from crm import models
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


def _format_bar(label: str, count: int, max_count: int, bar_width: int = 20) -> str:
    """Форматировать строку текстовой диаграммы."""
    filled = int((count / max_count) * bar_width) if max_count > 0 else 0
    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
    return f"{label:<10} |{bar}| {count}"


async def handle_clients_command(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Обработчик команды /clients - список клиентов по этапам."""
    models.init_db()
    log.info("clients_command", chat_id=chat_id)

    lines = ["<b>Клиенты по этапам воронки:</b>\n"]
    for stage in models.VALID_STAGES:
        clients = models.list_clients_by_stage(stage)
        lines.append(f"<b>{stage.upper()}</b> ({len(clients)}):")
        if clients:
            for c in clients[:10]:  # Максимум 10 на этап
                lines.append(f"  - {c['name']} (tg:{c['tg_id']})")
            if len(clients) > 10:
                lines.append(f"  ... и ещё {len(clients) - 10}")
        else:
            lines.append("  (пусто)")
        lines.append("")

    await _send_message(session, chat_id, "\n".join(lines))


async def handle_funnel_command(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Обработчик команды /funnel - статистика воронки."""
    models.init_db()
    log.info("funnel_command", chat_id=chat_id)

    stats = models.get_funnel_stats()
    max_count = max(stats.values()) if stats.values() else 1

    lines = ["<b>Воронка клиентов:</b>\n<pre>"]
    for stage in models.VALID_STAGES:
        count = stats.get(stage, 0)
        lines.append(_format_bar(stage, count, max_count))
    lines.append("</pre>")

    total = sum(stats.values())
    lines.append(f"\nВсего клиентов: {total}")

    await _send_message(session, chat_id, "\n".join(lines))
