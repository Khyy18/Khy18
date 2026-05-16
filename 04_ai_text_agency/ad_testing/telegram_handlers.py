"""Telegram-обработчики для дашборда A/B-тестирования.

Отправка отчетов по рекламным каналам в формате HTML через Telegram Bot API.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import aiohttp


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_API_URL = os.getenv("TELEGRAM_API_URL", "https://api.telegram.org")


def _bot_url(method: str) -> str:
    return f"{TELEGRAM_API_URL}/bot{TELEGRAM_TOKEN}/{method}"


def _format_channel_row(ch: dict) -> str:
    """Форматировать строку канала для HTML-таблицы."""
    conv_rate = ch.get("conversion_rate", 0.0)
    ctr = ch.get("ctr", 0.0)
    return (
        f"<b>{ch['name']}</b> [{ch['source_tag']}]\n"
        f"  Показы: {ch.get('impressions', 0)} | "
        f"Клики: {ch.get('clicks', 0)} | "
        f"Конверсии: {ch.get('conversions', 0)}\n"
        f"  CTR: {ctr:.1%} | "
        f"CR: {conv_rate:.1%} | "
        f"Расход: ${ch.get('spend', 0):.2f} | "
        f"Доход: ${ch.get('revenue', 0):.2f}"
    )


async def handle_ad_dashboard(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Отправить дашборд рекламных каналов в Telegram."""
    from ad_testing.engine import ABTestEngine

    engine = ABTestEngine()
    data = engine.get_dashboard_data()

    if not data["channels"]:
        text = "<b>Рекламные каналы</b>\n\nНет зарегистрированных каналов."
    else:
        lines = [f"<b>Рекламные каналы ({data['total_channels']})</b>\n"]
        for ch in data["channels"]:
            lines.append(_format_channel_row(ch))
        text = "\n\n".join(lines)

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with session.post(
            _bot_url("sendMessage"), data=payload, timeout=15
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[AD_TG] sendMessage статус {resp.status}: {body[:200]}")
    except aiohttp.ClientError as exc:
        print(f"[AD_TG] Сетевая ошибка sendMessage: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[AD_TG] Неожиданная ошибка sendMessage: {exc}")
