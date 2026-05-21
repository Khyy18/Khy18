"""Админ-хендлер для управления API-эндпоинтами через inline-кнопки."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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


class APIEditState(StatesGroup):
    waiting_url = State()


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


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\U0001f4ca \u0421\u0442\u0430\u0442\u0443\u0441", callback_data="api:status"),
            InlineKeyboardButton(text="\U0001f50d \u0422\u0435\u0441\u0442", callback_data="api:test"),
        ],
        [
            InlineKeyboardButton(text="\u270f\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c", callback_data="api:edit_menu"),
            InlineKeyboardButton(text="\U0001f504 \u0421\u0431\u0440\u043e\u0441", callback_data="api:reset"),
        ],
        [
            InlineKeyboardButton(text="\U0001f4cb \u0418\u0441\u0442\u043e\u0440\u0438\u044f", callback_data="api:history"),
        ],
    ])


def _edit_menu_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=key, callback_data=f"api:edit:{key}")]
        for key in DEFAULT_ENDPOINTS
    ]
    buttons.append([InlineKeyboardButton(text="\u21a9\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="api:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4e1 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="api:back")],
    ])


@router.message(Command("api"))
async def cmd_api_menu(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    text = card("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 API", "\U0001f4e1", ["\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435:"])
    await message.answer(text, parse_mode="HTML", reply_markup=_main_menu_kb())


@router.callback_query(F.data == "api:back")
async def cb_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await state.clear()
    text = card("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 API", "\U0001f4e1", ["\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435:"])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "api:status")
async def cb_status(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer("\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e...")
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
    text = card("API \u0421\u0442\u0430\u0442\u0443\u0441", "\U0001f4ca", lines)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_kb())


@router.callback_query(F.data == "api:test")
async def cb_test(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer("\u0422\u0435\u0441\u0442\u0438\u0440\u0443\u044e...")
    config = _load_config()
    endpoints = config.get("endpoints", DEFAULT_ENDPOINTS)
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
    summary = "\u2705 \u0412\u0441\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u044e\u0442" if all_ok else "\u26a0\ufe0f \u0415\u0441\u0442\u044c \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u044b"
    text = card("API \u0422\u0435\u0441\u0442", "\U0001f50d", results + ["", summary])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_kb())


@router.callback_query(F.data == "api:edit_menu")
async def cb_edit_menu(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    text = card("\u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c API", "\u270f\ufe0f", ["\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u044d\u043d\u0434\u043f\u043e\u0438\u043d\u0442:"])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_edit_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("api:edit:"))
async def cb_edit_endpoint(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        return
    key = callback.data.split(":")[2]
    config = _load_config()
    endpoints = config.get("endpoints", DEFAULT_ENDPOINTS)
    current_url = endpoints.get(key, "\u043d\u0435 \u0437\u0430\u0434\u0430\u043d")
    await state.set_state(APIEditState.waiting_url)
    await state.update_data(editing_key=key)
    text = card("\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435 API", "\U0001f527", [
        f"\u041a\u043b\u044e\u0447: <b>{key}</b>",
        f"\u0422\u0435\u043a\u0443\u0449\u0438\u0439 URL:",
        f"<code>{current_url}</code>",
        "",
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043d\u043e\u0432\u044b\u0439 URL:",
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_kb())
    await callback.answer()


@router.message(APIEditState.waiting_url)
async def handle_new_url(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data.get("editing_key", "")
    new_url = message.text.strip()
    if not new_url.startswith("http"):
        await message.answer("URL \u0434\u043e\u043b\u0436\u0435\u043d \u043d\u0430\u0447\u0438\u043d\u0430\u0442\u044c\u0441\u044f \u0441 http:// \u0438\u043b\u0438 https://")
        return
    config = _load_config()
    endpoints = config.get("endpoints", DEFAULT_ENDPOINTS.copy())
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
    status = f"\U0001f7e2 \u0420\u0430\u0431\u043e\u0442\u0430\u0435\u0442 ({ms:.0f}ms)" if alive else "\U0001f7e1 \u041d\u0435 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442 (\u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e)"
    text = card("API \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d", "\u2705", [
        f"\u041a\u043b\u044e\u0447: <b>{key}</b>",
        f"\u0421\u0442\u0430\u043b\u043e: <code>{new_url[:60]}</code>",
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}",
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=_back_kb())
    await state.clear()
    logger.info(f"API endpoint updated: {key} -> {new_url}")


@router.callback_query(F.data == "api:reset")
async def cb_reset(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    config = _load_config()
    config["endpoints"] = DEFAULT_ENDPOINTS.copy()
    history = config.get("history", [])
    history.insert(0, {
        "key": "ALL",
        "old": "custom",
        "new": "defaults",
        "timestamp": datetime.now().isoformat(),
    })
    config["history"] = history
    _save_config(config)
    text = card("API \u0441\u0431\u0440\u043e\u0448\u0435\u043d\u044b", "\U0001f504", [
        "\u0412\u0441\u0435 \u044d\u043d\u0434\u043f\u043e\u0438\u043d\u0442\u044b \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0435\u043d\u044b \u043a \u0434\u0435\u0444\u043e\u043b\u0442\u043d\u044b\u043c.",
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_kb())
    await callback.answer("\u0421\u0431\u0440\u043e\u0448\u0435\u043d\u043e")


@router.callback_query(F.data == "api:history")
async def cb_history(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        return
    config = _load_config()
    history = config.get("history", [])[:5]
    if not history:
        text = card("\u0418\u0441\u0442\u043e\u0440\u0438\u044f API", "\U0001f4cb", ["\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435 \u0431\u044b\u043b\u043e."])
    else:
        lines = []
        for h in history:
            dt = h.get("timestamp", "")[:16].replace("T", " ")
            lines.append(f"<b>{h['key']}</b> ({dt})")
            lines.append(f"  \u2192 {h['new'][:45]}")
            lines.append("")
        text = card("\u0418\u0441\u0442\u043e\u0440\u0438\u044f API", "\U0001f4cb", lines)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_kb())
    await callback.answer()
