"""Админ-хендлер для управления API-эндпоинтами парсеров через Telegram."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from bot.config import settings
from bot.ui.cards import card, DIVIDER

logger = logging.getLogger(__name__)
router = Router()

API_CONFIG_PATH = Path("data/api_config.json")

DEFAULT_ENDPOINTS = {
    "wb_catalog": "https://card.wb.ru/cards/v2/detail",
    "wb_search": "https://search.wb.ru/exactmatch/ru/common/v7/search",
    "wb_categories": "https://catalog.wb.ru/catalog/{category}/catalog",
    "ozon_search": "https://www.ozon.ru/api/composer-api.bx/page/json/v2",
    "ozon_product": "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2",
}


def _load_config() -> dict:
    if API_CONFIG_PATH.exists():
        try:
            return json.loads(API_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"endpoints": DEFAULT_ENDPOINTS.copy(), "history": []}


def _save_config(config: dict) -> None:
    API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    API_CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def _is_admin(user_id: int) -> bool:
    return user_id == settings.telegram_admin_id


async def _check_endpoint(url: str, timeout: float = 5.0) -> tuple[bool, float]:
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, follow_redirects=True)
            elapsed = (time.monotonic() - start) * 1000
            return resp.status_code < 500, elapsed
    except Exception:
        return False, 0.0


@router.message(Command("api_status"))
async def cmd_api_status(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    config = _load_config()
    endpoints = config.get("endpoints", DEFAULT_ENDPOINTS)

    lines = []
    for name, url in endpoints.items():
        alive, ms = await _check_endpoint(url)
        status = "\U0001f7e2" if alive else "\U0001f534"
        time_str = f"{ms:.0f}ms" if alive else "timeout"
        lines.append(f"{status} <b>{name}</b>")
        lines.append(f"   {url[:50]}")
        lines.append(f"   {time_str}")
        lines.append("")

    text = card("API \u0421\u0442\u0430\u0442\u0443\u0441", "\U0001f4e1", lines)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("api_set"))
async def cmd_api_set(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            f"{DIVIDER}\n"
            "\u0424\u043e\u0440\u043c\u0430\u0442: /api_set &lt;\u043a\u043b\u044e\u0447&gt; &lt;url&gt;\n\n"
            "\u041a\u043b\u044e\u0447\u0438:\n"
            "\u2022 wb_catalog\n"
            "\u2022 wb_search\n"
            "\u2022 wb_categories\n"
            "\u2022 ozon_search\n"
            "\u2022 ozon_product\n"
            f"{DIVIDER}",
            parse_mode="HTML",
        )
        return

    key = parts[1].lower()
    new_url = parts[2]

    config = _load_config()
    endpoints = config.get("endpoints", DEFAULT_ENDPOINTS.copy())

    if key not in DEFAULT_ENDPOINTS:
        await message.answer(f"\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u043a\u043b\u044e\u0447: {key}")
        return

    old_url = endpoints.get(key, "")
    endpoints[key] = new_url

    history = config.get("history", [])
    history.insert(0, {
        "key": key,
        "old": old_url,
        "new": new_url,
        "timestamp": datetime.now().isoformat(),
    })
    history = history[:20]

    config["endpoints"] = endpoints
    config["history"] = history
    _save_config(config)

    alive, ms = await _check_endpoint(new_url)
    status = "\U0001f7e2 \u0420\u0430\u0431\u043e\u0442\u0430\u0435\u0442" if alive else "\U0001f7e1 \u041d\u0435 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442 (\u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e)"

    text = card("API \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d", "\u2705", [
        f"\u041a\u043b\u044e\u0447: <b>{key}</b>",
        f"\u0411\u044b\u043b\u043e: {old_url[:40]}",
        f"\u0421\u0442\u0430\u043b\u043e: {new_url[:40]}",
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}",
    ])
    await message.answer(text, parse_mode="HTML")
    logger.info(f"API endpoint updated: {key} -> {new_url}")


@router.message(Command("api_test"))
async def cmd_api_test(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    config = _load_config()
    endpoints = config.get("endpoints", DEFAULT_ENDPOINTS)

    await message.answer("\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u044d\u043d\u0434\u043f\u043e\u0438\u043d\u0442\u044b...")

    results = []
    all_ok = True
    for name, url in endpoints.items():
        alive, ms = await _check_endpoint(url)
        if not alive:
            all_ok = False
        if alive:
            results.append(f"\U0001f7e2 {name}: {ms:.0f}ms")
        else:
            results.append(f"\U0001f534 {name}: FAIL")

    summary = "\u0412\u0441\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u044e\u0442" if all_ok else "\u0415\u0441\u0442\u044c \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u044b"
    text = card("API \u0422\u0435\u0441\u0442", "\U0001f50d", results + ["", summary])
    await message.answer(text, parse_mode="HTML")


@router.message(Command("api_reset"))
async def cmd_api_reset(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    config = _load_config()
    config["endpoints"] = DEFAULT_ENDPOINTS.copy()
    config.get("history", []).insert(0, {
        "key": "ALL",
        "old": "custom",
        "new": "defaults",
        "timestamp": datetime.now().isoformat(),
    })
    _save_config(config)

    text = card("API \u0441\u0431\u0440\u043e\u0448\u0435\u043d\u044b", "\U0001f504", [
        "\u0412\u0441\u0435 \u044d\u043d\u0434\u043f\u043e\u0438\u043d\u0442\u044b \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0435\u043d\u044b \u043a \u0434\u0435\u0444\u043e\u043b\u0442\u043d\u044b\u043c.",
        "",
        "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 /api_status \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c.",
    ])
    await message.answer(text, parse_mode="HTML")


@router.message(Command("api_history"))
async def cmd_api_history(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    config = _load_config()
    history = config.get("history", [])[:5]

    if not history:
        await message.answer("\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439 \u043f\u0443\u0441\u0442\u0430.")
        return

    lines = []
    for h in history:
        dt = h.get("timestamp", "")[:16].replace("T", " ")
        lines.append(f"<b>{h['key']}</b> ({dt})")
        lines.append(f"  \u2192 {h['new'][:45]}")
        lines.append("")

    text = card("\u0418\u0441\u0442\u043e\u0440\u0438\u044f API", "\U0001f4cb", lines)
    await message.answer(text, parse_mode="HTML")
