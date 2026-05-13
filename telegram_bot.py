"""Telegram-терминал для Zenith-Control Ultimate v3.

Long polling через aiohttp напрямую (без python-telegram-bot).
СТРОГО: каждое сообщение и callback_query, у которого from.id или chat.id
не равен TELEGRAM_CHAT_ID, отбрасывается молча. На callback_query чужого
пользователя отвечаем answerCallbackQuery с текстом «Доступ запрещён»,
но ничего в системе не меняем.

Главное меню v3 - 9 кнопок (4 ряда по 2 + 1 широкая снизу):

    📊 СТАТУС        📈 ПОЗИЦИИ
    🛡 AI-GATE       🎯 РЕЖИМЫ
    🔍 ПОЧЕМУ МИМО?  📝 ЛОГИ
    🤖 АНАЛИТИК      🔑 КЛЮЧИ API
    ⏯ СТАРТ/СТОП  ·  🚨 PANIC SELL

Кнопка 🤖 GROQ переехала из главного меню в подменю 📊 СТАТУС
(пассивный мониторинг квоты Groq API).

Все тексты для пользователя - на русском. Технические теги (vol_low,
ai_gate_veto и т.п.) в БД остаются английскими для совместимости с
кодом, при показе в UI переводятся через _ru_filter_tag.

Состояние state в v3 имеет форму:
    {
      'symbols': {symbol: {...}},
      'global': {..., 'started_epoch': time.time()},
      'instruments': {...},
    }
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

import ai_analyst
import ai_groq
import api_engine  # noqa: F401  # legacy shim
import config
import memory
from exchanges import get_adapter


# Единый адаптер биржи (выбирается через config.EXCHANGE).
EXCHANGE = get_adapter(config.EXCHANGE)


# --- Callback data ids (короткие, чтобы влезали в ограничение Telegram 64 байта) ---
CB_STATUS = "zc:status"
CB_POSITIONS = "zc:positions"
CB_AIGATE = "zc:aigate"
CB_REGIMES = "zc:regimes"
CB_WHY = "zc:why"
CB_LOGS = "zc:logs"
CB_STARTSTOP = "zc:startstop"
CB_PANIC = "zc:panic"
CB_KEYS = "zc:keys"
CB_GROQ = "zc:groq"
CB_GROQ_REFRESH = "zc:groq_refresh"

# Аналитик (FEAT-007 / C3): подменю и FSM свободного вопроса.
CB_ANALYST = "zc:analyst"
CB_ANALYST_ASK = "zc:an_ask"
CB_ANALYST_EX1 = "zc:an_ex1"
CB_ANALYST_EX2 = "zc:an_ex2"
CB_ANALYST_EX3 = "zc:an_ex3"
CB_ANALYST_EX4 = "zc:an_ex4"
CB_ANALYST_CANCEL = "zc:an_cancel"
# Объединённое подменю «Старт/Стоп · PANIC SELL» — широкая нижняя кнопка
# главного меню. Старые подменю CB_STARTSTOP и CB_PANIC доступны переходом
# внутрь.
CB_STARTSTOP_PANIC = "zc:ssp"

# Заглушки для следующих этапов — кнопки появляются сейчас, реальные
# обработчики будут добавлены в соответствующих FEAT-ах.
CB_AGGR_MENU = "zc:aggr"        # FEAT-003: слайдер агрессивности (реализовано)
CB_AGGR_SET_PREFIX = "zc:aggr_set:"      # + key (conservative/medium/aggressive)
CB_AGGR_CONFIRM_PREFIX = "zc:aggr_ok:"   # + key
CB_BLOCKS = "zc:blocks"          # FEAT-004: запретный список (manual + auto)
# FEAT-004: подкоманды меню запретов.
CB_BLOCKS_ADD = "zc:blk_add"
CB_BLOCKS_CANCEL = "zc:blk_no"
CB_BLOCKS_REMOVE_PREFIX = "zc:blk_rm:"     # + "<type>:<symbol>"
CB_BLOCKS_DURATION_PREFIX = "zc:blk_d:"    # + "<hours_or_inf>"
CB_BLOCKS_AUTOSETTINGS = "zc:blk_set"
CB_BLOCKS_AUTOSET_PREFIX = "zc:blk_set_v:"  # + "<field>:<value>" (s=streak, h=hours)
CB_EXPORT_ENV = "zc:env_export"  # FEAT-005: экспорт настроек .env
CB_PAIRS = "zc:pairs"            # FEAT-006: статистика по парам
CB_PAIR_PICKER = "zc:pair_pick"  # FEAT-006: список пар «Подробнее ▾»
CB_PAIR_DETAIL_PREFIX = "zc:pair:"        # + symbol
CB_PAIR_BLOCK_PREFIX = "zc:pair_blk:"     # + symbol → перевод в FSM блока
CB_BT_MENU = "zc:bt"             # FEAT-008: Backtest UI
CB_BT_PERIOD_PREFIX = "zc:bt_p:"  # + "7"/"30"/"90"
CB_BT_RUN = "zc:bt_run"
CB_BT_CSV = "zc:bt_csv"
CB_BT_BACK = "zc:bt_back"

# Подменю / действия.
CB_TOGGLE_DRY_RUN = "zc:toggle_dry"
CB_AIGATE_MENU = "zc:aigate_menu"
CB_AIGATE_RECENT = "zc:aigate_recent"
CB_AIGATE_SET_OFF = "zc:ag_off"
CB_AIGATE_SET_SHADOW = "zc:ag_shadow"
CB_AIGATE_SET_ACTIVE = "zc:ag_active"
CB_AIGATE_CONFIRM_PREFIX = "zc:ag_ok:"  # + mode

CB_MODE_SWITCH = "zc:mode_switch"
CB_MODE_SWITCH_OK = "zc:mode_sw_ok"
CB_MODE_SWITCH_NO = "zc:mode_sw_no"

CB_KILL_CLEAR = "zc:kill_clear"

CB_START_BOT = "zc:bot_start"
CB_STOP_BOT = "zc:bot_stop"
CB_BACK_MAIN = "zc:back_main"

CB_PANIC_CONFIRM = "zc:panic_ok"
CB_PANIC_CANCEL = "zc:panic_no"

CB_LOGS_REFRESH = "zc:logs_refresh"
CB_LOGS_ERRORS = "zc:logs_errors"
CB_LOGS_AIGATE = "zc:logs_aigate"

CB_WHY_AI = "zc:why_ai"
CB_WHY_GATE_ONLY = "zc:why_gate"

# Ключи API (FSM). Префикс zc:key:<env_name>.
CB_KEY_PREFIX = "zc:key:"
# Подтверждение (после ввода значения).
CB_KEY_CONFIRM_PREFIX = "zc:key_ok:"  # + env_name
CB_KEY_CANCEL = "zc:key_no"


# --- FSM для замены ключей (per-chat_id) ---
# Структура:
#   {chat_id: {"env_name": str, "pending_value": str | None, "started": float}}
# pending_value == None  -> ждём сообщение с ключом
# pending_value == str   -> ждём подтверждение через инлайн-кнопку
_key_fsm_state: dict[int, dict[str, Any]] = {}

_KEY_FSM_TIMEOUT_SEC = 300  # 5 минут

# --- FSM для добавления ручного блока (FEAT-004 / B2) ---
# Структура:
#   {chat_id: {"step": "await_symbol" | "await_duration",
#              "symbol": str | None, "started": float}}
# step == "await_symbol"   -> ждём текстовое сообщение с тикером
# step == "await_duration" -> ждём callback с длительностью
_blocks_fsm_state: dict[int, dict[str, Any]] = {}
_BLOCKS_FSM_TIMEOUT_SEC = 300  # 5 минут

# --- FSM для AI-Аналитика (FEAT-007 / C3) ---
# Структура:
#   {chat_id: {"mode": "awaiting_question", "started": float}}
_analyst_fsm_state: dict[int, dict[str, Any]] = {}
_ANALYST_FSM_TIMEOUT_SEC = 300  # 5 минут

# Пред-определённые вопросы примеров (CB_ANALYST_EX1..EX4).
_ANALYST_EXAMPLES: list[tuple[str, str]] = [
    (CB_ANALYST_EX1, "Почему я слил на XRP?"),
    (CB_ANALYST_EX2, "Какая моя худшая стратегия?"),
    (CB_ANALYST_EX3, "Когда AI-Gate ошибался?"),
    (CB_ANALYST_EX4, "Стоит ли мне перейти на РЕАЛ?"),
]

# Rate-limit для уведомлений о fail-CLOSED блокировке (Groq недоступен).
# symbol → unix timestamp последней отправки уведомления.
_gate_error_notify_last_ts: dict[str, float] = {}


# --- Маппинги для UI-текстов -------------------------------------------------

_FILTER_TAG_RU = {
    "vol_low": "Низкая волатильность",
    "vol_confirm_weak": "Слабый объём на пробое",
    "breakout": "Нет пробоя уровня",
    "trend_1d": "Не совпадает с дневным трендом",
    "trend_4h": "Не совпадает с 4-часовым трендом",
    "adx_weak": "Слабый тренд (ADX)",
    "blackout": "Макро-blackout",
    "regime_crisis": "Режим «Кризис»",
    "insufficient_data": "Недостаточно данных",
    "ai_gate_veto": "AI-Gate блокировка",
    "ai_gate_error": "AI-Gate: ошибка проверки",
    "mr_regime_not_ranging": "Рынок не в боковике",
    "mr_blackout": "Макро-blackout (отскок)",
    "mr_no_band_touch": "Не достиг полосы Боллинджера",
    "mr_rsi_neutral": "RSI в нейтральной зоне",
    "mr_adx_trending": "Слишком сильный тренд для отскока",
    "mr_vol_low": "Низкая волатильность (15м)",
}


def _ru_filter_tag(tag: str) -> str:
    """Перевод технического тега в русское описание для показа пользователю.
    Fallback: исходный тег как есть."""
    if not tag:
        return "-"
    return _FILTER_TAG_RU.get(str(tag), str(tag))


def _ru_regime(regime: str) -> str:
    """TRENDING/RANGING/CRISIS -> Тренд/Боковик/Кризис."""
    r = str(regime or "").upper()
    return {"TRENDING": "Тренд", "RANGING": "Боковик", "CRISIS": "Кризис"}.get(
        r, regime or "-"
    )


def _regime_emoji(regime: str) -> str:
    """Эмодзи для режима: TRENDING=🟢, RANGING=🔴, CRISIS=⚪, иначе ⚙."""
    r = str(regime or "").upper()
    return {"TRENDING": "🟢", "RANGING": "🔴", "CRISIS": "⚪"}.get(r, "⚙")


def _ru_verdict(v: str) -> str:
    """approve -> одобрено, veto -> veto, error -> ошибка."""
    vv = str(v or "").lower()
    return {"approve": "одобрено", "veto": "veto", "error": "ошибка"}.get(vv, vv)


# --- Визуальные хелперы -----------------------------------------------------
# Низкоуровневые форматтеры карточек: горизонтальные разделители, числа с
# тонким пробелом U+202F и истинным минусом U+2212, статусные индикаторы,
# прогресс-бары квот, стрелки для PnL и направления сделки. Чистые функции
# без I/O. HTML-теги добавляет вызывающий код (parse_mode=HTML стоит на
# уровне send_message).

HR = "━" * 24
SUBHR = "─" * 24

_NBSP = "\u202f"   # узкий неразрывный пробел (разделитель тысяч)
_MINUS = "\u2212"  # типографский минус


def _card(title: str, emoji: str, body_lines: list[str]) -> str:
    """Карточка в едином стиле: HR / "{emoji} {title}" / HR / body / HR.

    Возвращает обычный текст без HTML-обёрток. Вызывающий может обернуть
    нужные строки в <b>...</b> до передачи в send_message.
    """
    head = f"{emoji} {title}".strip() if emoji else (title or "")
    parts: list[str] = [HR, head, HR]
    parts.extend(body_lines or [])
    parts.append(HR)
    return "\n".join(parts)


def _subhr_line() -> str:
    """Тонкий разделитель внутри карточки."""
    return SUBHR


def _label(name: str, value: str, pad: int = 12) -> str:
    """Строка вида "<имя ровно pad>  <значение>" для табличного вида."""
    name_s = str(name or "")
    if pad < 0:
        pad = 0
    if len(name_s) < pad:
        name_s = name_s + " " * (pad - len(name_s))
    return f"{name_s} {value}"


def _fmt_num(value: Any, decimals: int = 2) -> str:
    """Число с разделителем тысяч U+202F и истинным минусом U+2212.

    Не-числа возвращают "-".
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = _MINUS if v < 0 else ""
    abs_v = abs(v)
    s = f"{abs_v:,.{max(0, int(decimals))}f}".replace(",", _NBSP)
    return f"{sign}{s}"


def _pnl_arrow(value: Any) -> str:
    """Стрелка PnL: ▲ для >0, ▼ для <0, · для нуля/невалидного."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "·"
    if v > 0:
        return "▲"
    if v < 0:
        return "▼"
    return "·"


def _fmt_pnl(value: Any, decimals: int = 2) -> str:
    """PnL со стрелкой направления и числом в едином формате."""
    arrow = _pnl_arrow(value)
    try:
        float(value)
    except (TypeError, ValueError):
        return f"{arrow} -"
    return f"{arrow} {_fmt_num(value, decimals)}"


def _fmt_pct(value: Any, decimals: int = 2) -> str:
    """Процент со стрелкой направления и знаком; "·" для нуля."""
    arrow = _pnl_arrow(value)
    try:
        float(value)
    except (TypeError, ValueError):
        return f"{arrow} -%"
    return f"{arrow} {_fmt_num(value, decimals)}%"


def _dir_arrow(side: Any) -> str:
    """Направление сделки: 'LONG ↗' / 'SHORT ↘'. Иначе - исходник."""
    s = str(side or "").strip().upper()
    if s == "LONG":
        return "LONG ↗"
    if s == "SHORT":
        return "SHORT ↘"
    return s or "-"


def _status_dot(level: Any) -> str:
    """Точечный индикатор статуса:
    'ok' -> 🟢, 'warn' -> 🟡, 'bad' -> 🔴, 'off' -> ⚪.
    Любой другой ключ возвращает ⚪.
    """
    return {
        "ok": "🟢",
        "warn": "🟡",
        "bad": "🔴",
        "off": "⚪",
    }.get(str(level or "").strip().lower(), "⚪")


def _progress_bar_10(used: Any, limit: Any) -> str:
    """Прогресс-бар длиной ровно 10 символов: ▰ заполнено, ▱ пусто.

    При limit<=0 или некорректных аргументах возвращает 10 пустых клеток.
    used клипуется в диапазон [0, limit].
    """
    try:
        u = float(used)
        lim = float(limit)
    except (TypeError, ValueError):
        return "▱" * 10
    if lim <= 0:
        return "▱" * 10
    frac = u / lim
    if frac < 0.0:
        frac = 0.0
    if frac > 1.0:
        frac = 1.0
    filled = int(round(frac * 10))
    if filled < 0:
        filled = 0
    if filled > 10:
        filled = 10
    return ("▰" * filled) + ("▱" * (10 - filled))


# --- Вспомогательные ---------------------------------------------------------

def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


def _g(state: dict[str, Any]) -> dict[str, Any]:
    """Вернуть словарь «глобального» раздела state (v2/v3: state['global'])."""
    g = state.get("global") if isinstance(state, dict) else None
    if isinstance(g, dict):
        return g
    return state


def set_keyboard() -> dict[str, Any]:
    """Главная reply-клавиатура v3: 9 кнопок (4 ряда по 2 + 1 широкая снизу)."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 СТАТУС", "callback_data": CB_STATUS},
                {"text": "📈 ПОЗИЦИИ", "callback_data": CB_POSITIONS},
            ],
            [
                {"text": "🛡 AI-GATE", "callback_data": CB_AIGATE},
                {"text": "🎯 РЕЖИМЫ", "callback_data": CB_REGIMES},
            ],
            [
                {"text": "🔍 ПОЧЕМУ МИМО?", "callback_data": CB_WHY},
                {"text": "📝 ЛОГИ", "callback_data": CB_LOGS},
            ],
            [
                {"text": "🤖 АНАЛИТИК", "callback_data": CB_ANALYST},
                {"text": "🔑 КЛЮЧИ API", "callback_data": CB_KEYS},
            ],
            [
                {"text": "⏯ СТАРТ/СТОП  ·  🚨 PANIC SELL",
                 "callback_data": CB_STARTSTOP_PANIC},
            ],
        ]
    }


async def send_message(
    session: aiohttp.ClientSession,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
    chat_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram. По умолчанию - единственному разрешённому chat_id."""
    if not config.TELEGRAM_TOKEN:
        print("[TG] TELEGRAM_TOKEN не задан - пропускаем отправку")
        return None
    payload: dict[str, Any] = {
        "chat_id": chat_id if chat_id is not None else config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[TG] sendMessage статус {resp.status}: {body[:200]}")
                return None
            return await resp.json()
    except aiohttp.ClientError as exc:
        print(f"[TG] Сетевая ошибка sendMessage: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Неожиданная ошибка sendMessage: {exc}")
        return None


async def send_document(
    session: aiohttp.ClientSession,
    file_bytes: bytes,
    filename: str,
    caption: Optional[str] = None,
    chat_id: Optional[int] = None,
) -> bool:
    """Отправить файл через sendDocument (multipart/form-data).

    Используется в B3 (экспорт .env-снимка) и D (отчёты бэктеста).
    Все ошибки логируются и не пробрасываются - возвращает False.
    parse_mode для caption фиксирован в HTML, как и в send_message.
    """
    if not config.TELEGRAM_TOKEN:
        print("[TG] TELEGRAM_TOKEN не задан - пропускаем sendDocument")
        return False
    target_chat = chat_id if chat_id is not None else config.TELEGRAM_CHAT_ID
    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", str(target_chat))
        if caption:
            form.add_field("caption", caption)
            form.add_field("parse_mode", "HTML")
        form.add_field(
            "document",
            file_bytes if isinstance(file_bytes, (bytes, bytearray)) else bytes(file_bytes),
            filename=filename,
            content_type="application/octet-stream",
        )
        async with session.post(
            _bot_url("sendDocument"), data=form, timeout=30
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[TG] sendDocument статус {resp.status}: {body[:200]}")
                return False
            return True
    except aiohttp.ClientError as exc:
        print(f"[TG] Сетевая ошибка sendDocument: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Неожиданная ошибка sendDocument: {exc}")
        return False


async def notify_trade_blocked_by_gate_error(
    session: aiohttp.ClientSession,
    *,
    symbol: str,
    side: str,
    strategy_name: str,
    price: float,
    error_reason: str,
) -> None:
    """Push-уведомление о fail-CLOSED блокировке сделки (Groq недоступен).

    Отправляется ТОЛЬКО в active-режиме при gate.verdict=error.
    Встроен rate-limit: не более 1 уведомления за 5 минут на одну пару.
    Ошибки отправки логируются, main-loop не ломается.
    """
    if not getattr(config, "NOTIFY_ON_GATE_ERROR_BLOCK", True):
        return
    now_ts = time.time()
    last_ts = _gate_error_notify_last_ts.get(symbol, 0.0)
    if now_ts - last_ts < 300:
        return
    _gate_error_notify_last_ts[symbol] = now_ts

    is_long = str(side).lower() in ("buy", "long")
    side_label = "LONG" if is_long else "SHORT"
    raw_reason = error_reason or ""
    reason_txt = (raw_reason[:200] + "…") if len(raw_reason) > 200 else raw_reason
    utc_now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = [
        _label("Пара", str(symbol)),
        _label("Сторона", f"{_dir_arrow(side_label)} (планировалась)"),
        _label("Сигнал", str(strategy_name)),
        _label("Цена", _fmt_num(price, 4)),
        _subhr_line(),
        f"AI-GATE: {_status_dot('warn')} ошибка",
        _label("Причина", reason_txt),
        _subhr_line(),
        "Это не потеря — сделка не открыта",
        "из соображений безопасности.",
        "Перейти в наблюдение:",
        "  🛡 AI-GATE → «Перейти в наблюдение»",
        _subhr_line(),
        _label("⏱", utc_now),
    ]
    text = _card(
        "СДЕЛКА ЗАБЛОКИРОВАНА (Groq недоступен)",
        "⚠️",
        body,
    )
    try:
        await send_message(session, text, reply_markup=set_keyboard())
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] ошибка notify_trade_blocked_by_gate_error: {exc}")


async def delete_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    message_id: int,
) -> bool:
    """Удалить сообщение через deleteMessage. True - если успешно."""
    if not config.TELEGRAM_TOKEN:
        return False
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        async with session.post(
            _bot_url("deleteMessage"), data=payload, timeout=10
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(
                    f"[TG] deleteMessage статус {resp.status}: {body[:200]}"
                )
                return False
            return True
    except aiohttp.ClientError as exc:
        print(f"[TG] Сетевая ошибка deleteMessage: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Неожиданная ошибка deleteMessage: {exc}")
        return False


async def edit_message_text(
    session: aiohttp.ClientSession,
    chat_id: int,
    message_id: int,
    new_text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> bool:
    """Отредактировать текст ранее отправленного сообщения через editMessageText.

    Используется в FEAT-008: после старта бэктеста бот шлёт «🔄 Идёт расчёт…»
    и по завершении подменяет это же сообщение на финальный отчёт без
    спама в чат. parse_mode/disable_web_page_preview совпадают с
    `send_message`. Все ошибки логируются, исключения наружу не выбрасывает -
    возвращает False при любой неудаче.
    """
    if not config.TELEGRAM_TOKEN:
        print("[TG] TELEGRAM_TOKEN не задан - пропускаем editMessageText")
        return False
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": new_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        async with session.post(
            _bot_url("editMessageText"), data=payload, timeout=15
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(
                    f"[TG] editMessageText статус {resp.status}: {body[:200]}"
                )
                return False
            return True
    except aiohttp.ClientError as exc:
        print(f"[TG] Сетевая ошибка editMessageText: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Неожиданная ошибка editMessageText: {exc}")
        return False


async def answer_callback(
    session: aiohttp.ClientSession,
    callback_id: str,
    text: str = "",
    show_alert: bool = False,
) -> None:
    """answerCallbackQuery - убирает «часики» у нажатой кнопки."""
    if not config.TELEGRAM_TOKEN:
        return
    payload = {
        "callback_query_id": callback_id,
        "text": text[:200],
        "show_alert": bool(show_alert),
    }
    try:
        async with session.post(
            _bot_url("answerCallbackQuery"), data=payload, timeout=10
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[TG] answerCallbackQuery статус {resp.status}: {body[:200]}")
    except aiohttp.ClientError as exc:
        print(f"[TG] Сетевая ошибка answerCallbackQuery: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Неожиданная ошибка answerCallbackQuery: {exc}")


def _is_authorized(update: dict[str, Any]) -> bool:
    """True только если from.id И chat.id принадлежат единственному владельцу."""
    allowed = config.TELEGRAM_CHAT_ID
    if not allowed:
        return False
    try:
        msg = update.get("message") or update.get("edited_message")
        if msg:
            from_id = (msg.get("from") or {}).get("id")
            chat_id = (msg.get("chat") or {}).get("id")
            return from_id == allowed and chat_id == allowed
        cb = update.get("callback_query")
        if cb:
            from_id = (cb.get("from") or {}).get("id")
            chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
            if chat_id is None:
                return from_id == allowed
            return from_id == allowed and chat_id == allowed
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка проверки авторизации: {exc}")
    return False


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_uptime(seconds: float) -> str:
    """Uptime вида 'Nд Nч Nм' (или 'Nч Nм' если меньше суток)."""
    secs = int(max(0, seconds))
    if secs < 60:
        return f"{secs}с"
    minutes, _ = divmod(secs, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days > 0:
        return f"{days}д {hours}ч {minutes}м"
    return f"{hours}ч {minutes}м"


def _format_remaining(until: Optional[datetime]) -> str:
    if until is None:
        return "без срока"
    now = datetime.now(tz=timezone.utc)
    delta = until - now
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "истекает сейчас"
    hours, rem = divmod(secs, 3600)
    minutes, _ = divmod(rem, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}д {hours}ч"
    return f"{hours}ч {minutes}м"


# --- Запись в .env (атомарная, с правами 0o600) ----------------------------

def _env_file_path() -> str:
    """Путь к .env. Предпочитаем /opt/zenith/.env (prod), fallback - рядом."""
    prod = "/opt/zenith/.env"
    if os.path.exists(prod):
        return prod
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".env"
    )


def _write_env_var(name: str, value: str) -> bool:
    """Атомарно записать (или обновить) переменную в .env.

    Никогда НЕ логируем значение value - ни в stdout, ни в журнал.
    Возвращаем True если запись успешна, False иначе.
    """
    path = _env_file_path()
    try:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except FileNotFoundError:
            lines = []

        prefix = f"{name}="
        new_line = f"{name}={value}\n"
        found = False
        out: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith(prefix):
                if not found:
                    out.append(new_line)
                    found = True
                # дубли - игнорируем
            else:
                out.append(line)
        if not found:
            if out and not out[-1].endswith("\n"):
                out[-1] = out[-1] + "\n"
            out.append(new_line)

        dir_path = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp_path = tempfile.mkstemp(
            prefix=".env.", dir=dir_path, text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                tf.writelines(out)
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        print(f"[TG] _write_env_var: обновлена переменная {name} (длина={len(value)})")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] _write_env_var({name}): ошибка записи: {exc}")
        return False


# --- FEAT-005 / B3: экспорт настроек .env с маскированием секретов ---------
# Регулярка имени переменной, значение которой нужно замаскировать. Матчит
# суффиксы _KEY / _SECRET / _TOKEN, а также самостоятельное PASSPHRASE.
_SECRET_NAME_RE = re.compile(r"(?i)(_KEY|_SECRET|_TOKEN|PASSPHRASE)")
# Строка вида KEY=VALUE: валидное имя переменной, остальное - значение.
_ENV_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _mask_env_line(line: str) -> str:
    """Замаскировать секрет в одной строке .env.

    Правила:
      * пустые строки и строки-комментарии (начинаются с `#`) возвращаются
        как есть (без правок);
      * если строка имеет форму ``KEY=VALUE`` и имя ``KEY`` матчится
        ``_SECRET_NAME_RE`` (case-insensitive) - правая часть заменяется
        на ``***``;
      * все остальные строки возвращаются без изменений.

    Сохраняется завершающий перенос строки, если он был.
    """
    if line is None:
        return ""
    # Сохраняем завершающий перенос строки, чтобы вернуть ровно тот же формат.
    nl = ""
    body = line
    if body.endswith("\r\n"):
        nl = "\r\n"
        body = body[:-2]
    elif body.endswith("\n"):
        nl = "\n"
        body = body[:-1]

    stripped = body.lstrip()
    if not stripped or stripped.startswith("#"):
        return body + nl

    m = _ENV_KV_RE.match(body)
    if not m:
        return body + nl
    key = m.group(1)
    if _SECRET_NAME_RE.search(key):
        return f"{key}=***" + nl
    return body + nl


def _parse_env_example_keys() -> list[str]:
    """Прочитать .env.example и вернуть имена ключей в порядке появления.

    Используется как белый список для fallback-режима экспорта (когда .env
    отсутствует на диске и собирается из ``os.environ``).
    Закомментированные строки (``# KEY=...``) тоже учитываются - так в
    .env.example документируются опциональные переменные.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env.example")
    keys: list[str] = []
    seen: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                # Снимаем ведущий `#` чтобы поймать опциональные ключи.
                if line.startswith("#"):
                    line = line.lstrip("#").strip()
                if not line or "=" not in line:
                    continue
                m = _ENV_KV_RE.match(line)
                if not m:
                    continue
                key = m.group(1)
                if key in seen:
                    continue
                seen.add(key)
                keys.append(key)
    except OSError:
        return []
    return keys


def _build_env_export() -> bytes:
    """Собрать снимок .env с маскированными секретами.

    Алгоритм:
      1. Если файл ``_env_file_path()`` существует - читаем построчно и
         пропускаем каждую строку через ``_mask_env_line`` (комментарии,
         пустые строки и порядок строк сохраняются как есть).
      2. Если файла нет - собираем снимок из ``os.environ`` по белому
         списку имён из ``.env.example`` (порядок появления). Отсутствующие
         в окружении ключи пропускаются.
      3. В начало добавляется заголовок с временем UTC и пометкой о
         маскировке.

    Возвращает ``bytes`` в utf-8. Никогда не пишет реальные секреты в
    stdout/log - только сами имена переменных.
    """
    iso_utc = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (
        "# Zenith-Control v3 — экспорт настроек\n"
        f"# Сгенерировано: {iso_utc}\n"
        "# Секреты замаскированы как ***\n"
        "\n"
    )

    body_text = ""
    path = _env_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                masked_lines = [_mask_env_line(raw) for raw in fh]
            body_text = "".join(masked_lines)
            # Гарантируем перевод строки на конце.
            if body_text and not body_text.endswith("\n"):
                body_text += "\n"
        except OSError as exc:
            print(f"[TG] _build_env_export: ошибка чтения {path}: {exc}")
            body_text = ""

    if not body_text:
        # Fallback: синтезируем из os.environ по списку ключей .env.example.
        keys = _parse_env_example_keys()
        out: list[str] = []
        for key in keys:
            if key not in os.environ:
                continue
            value = os.environ[key]
            if _SECRET_NAME_RE.search(key):
                out.append(f"{key}=***\n")
            else:
                out.append(f"{key}={value}\n")
        body_text = "".join(out)

    return (header + body_text).encode("utf-8")


# --- Заглушки для следующих этапов -----------------------------------------
# Новые кнопки FEAT-002 показываются уже сейчас; их обработчики появятся в
# FEAT-003/004/005/006/008. Чтобы не плодить веточки в диспетчере на каждый
# этап, отдаём единый плейсхолдер с указанием стадии.

def _stage_placeholder(stage: str) -> str:
    """Единый плейсхолдер для кнопок будущих этапов."""
    return _card(
        f"Этап {stage}",
        "🛠",
        ["Будет добавлено в этапе " + stage],
    )


async def _handle_env_export(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> Optional[str]:
    """Реальный обработчик кнопки 📤 Экспорт .env (FEAT-005 / B3).

    Собирает снимок настроек через ``_build_env_export`` (секреты заменены
    на ``***``) и шлёт его через ``send_document`` с короткой карточкой в
    caption. Возвращает None при успехе (документ уже отправлен) или
    строку-описание ошибки - её диспетчер пошлёт обычным send_message.
    """
    try:
        file_bytes = _build_env_export()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] _handle_env_export: ошибка _build_env_export: {exc}")
        return _card(
            "Экспорт .env",
            "📤",
            ["Не удалось собрать снимок настроек.", str(exc)],
        )

    if not file_bytes or len(file_bytes) < 4:
        return _card(
            "Экспорт .env",
            "📤",
            ["Снимок настроек пуст: ни .env, ни os.environ"
             " не содержат известных ключей."],
        )

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f".env-export-{ts}.txt"
    caption_html = _card(
        "Экспорт .env",
        "📤",
        [
            "Секреты замаскированы как ***.",
            "Файл можно загрузить на новом сервере",
            "как стартовую точку настройки.",
            _subhr_line(),
            _label("Размер", f"{len(file_bytes)} байт"),
            _label("Файл", filename),
        ],
    )

    ok = await send_document(
        session,
        file_bytes,
        filename,
        caption=caption_html,
        chat_id=chat_id,
    )
    if not ok:
        return _card(
            "Экспорт .env",
            "📤",
            ["Не удалось отправить файл (sendDocument).",
             "Проверьте логи бота."],
        )
    # Документ уже доставлен - возвращаем None, чтобы диспетчер не слал
    # дополнительное сообщение.
    return None


async def _handle_pairs_stub(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Заглушка кнопки 📈 По парам (FEAT-006 / C2) — оставлена для
    обратной совместимости callback-имён, реальный обработчик ниже."""
    return _stage_placeholder("C2 (статистика по парам)")


# --- FEAT-006 / C2: статистика по парам (per-symbol stats) -----------------
# `📈 По парам` доступно из 📊 СТАТУС. Сводная таблица за 30 дней по всем
# config.SYMBOLS с цветовыми индикаторами:
#   🟢  winrate >= 60% AND pnl > 0
#   🔴  winrate < 40% OR pnl < -10
#   ⚪  меньше 5 сделок (мало данных)
#   🟡  иначе
# Из таблицы по кнопке `Подробнее ▾` открывается выбор символа; на per-symbol
# detail-странице показываются profit factor, среднее время удержания (если
# можно вычислить), топ причин убытков и AI-Gate статистика по символу. На
# detail доступна кнопка «🚫 Заблокировать» — она ставит symbol в FSM
# из FEAT-004 сразу на шаг выбора длительности.

def _pair_dot(count: int, winrate: float, pnl_sum: float) -> str:
    """Цветовая точка по правилам FEAT-006."""
    if count < 5:
        return _status_dot("off")
    if winrate >= 60.0 and pnl_sum > 0.0:
        return _status_dot("ok")
    if winrate < 40.0 or pnl_sum < -10.0:
        return _status_dot("bad")
    return _status_dot("warn")


def _short_symbol(symbol: str) -> str:
    """Короткое имя символа (без хвоста USDT) для компактных таблиц."""
    s = str(symbol or "-")
    return s[: -len("USDT")] if s.endswith("USDT") else s


async def _handle_per_symbol_stats(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Карточка `📈 Статистика · 30д` — таблица по всем парам + Итого."""
    try:
        rows = memory.get_per_symbol_stats(30)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_per_symbol_stats: {exc}")
        rows = []

    body: list[str] = []
    # Заголовок таблицы (моноширинный, выровнен по ширине _short_symbol).
    body.append("Символ      Сделок  Винрейт      PnL")
    body.append("─" * 36)

    if not rows:
        body.append("(нет данных за период)")
    else:
        for r in rows:
            sym_short = _short_symbol(str(r.get("symbol") or "-"))
            count = int(r.get("count") or 0)
            winrate = float(r.get("winrate") or 0.0)
            pnl_sum = float(r.get("pnl_sum") or 0.0)
            dot = _pair_dot(count, winrate, pnl_sum)
            body.append(
                f"{dot} {sym_short:<6}  "
                f"{count:>5}   "
                f"{_fmt_num(winrate, 1):>6}%   "
                f"{_fmt_pnl(pnl_sum, 1)}"
            )

    body.append(_subhr_line())
    total_count = sum(int(r.get("count") or 0) for r in rows)
    total_wins = sum(int(r.get("wins") or 0) for r in rows)
    total_losses = sum(int(r.get("losses") or 0) for r in rows)
    total_decided = total_wins + total_losses
    total_winrate = (
        (total_wins / total_decided * 100.0) if total_decided else 0.0
    )
    total_pnl = sum(float(r.get("pnl_sum") or 0.0) for r in rows)
    body.append(
        f"Итого: сделок {total_count}, "
        f"винрейт {_fmt_num(total_winrate, 1)}%, "
        f"PnL {_fmt_pnl(total_pnl, 1)}"
    )

    text = _card("Статистика · 30д", "📈", body)
    inline = {
        "inline_keyboard": [
            [{"text": "Подробнее ▾", "callback_data": CB_PAIR_PICKER}],
            [{"text": "◀ Назад", "callback_data": CB_STATUS}],
        ]
    }
    return text, inline


async def _handle_pair_picker(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Сетка кнопок: выбор пары для перехода в detail-карточку."""
    body = [
        "Выберите пару для подробной статистики.",
        _subhr_line(),
        "Период анализа: последние 30 дней.",
    ]
    text = _card("Подробнее по парам", "📈", body)
    inline_rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for symbol in config.SYMBOLS:
        row.append({
            "text": _short_symbol(symbol),
            "callback_data": f"{CB_PAIR_DETAIL_PREFIX}{symbol}",
        })
        if len(row) == 2:
            inline_rows.append(row)
            row = []
    if row:
        inline_rows.append(row)
    inline_rows.append([
        {"text": "◀ К таблице", "callback_data": CB_PAIRS},
    ])
    return text, {"inline_keyboard": inline_rows}


def _format_avg_holding(symbol: str) -> Optional[str]:
    """Среднее время удержания закрытых сделок за 30 дней.

    Считаем разницу `closed_ts - ts` для всех закрытых сделок символа
    из последних 30 суток. Если в выборке нет валидных пар времени —
    возвращаем None (UI скрывает строку).
    """
    sym = str(symbol or "-").strip().upper()
    try:
        trades = memory.get_trades_since(30)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_trades_since(30): {exc}")
        return None
    deltas: list[float] = []
    for t in trades:
        if str(t.get("symbol") or "").upper() != sym:
            continue
        closed = t.get("closed_ts")
        opened = t.get("ts")
        if not closed or not opened:
            continue
        dt_open = _parse_iso(str(opened))
        dt_close = _parse_iso(str(closed))
        if dt_open is None or dt_close is None:
            continue
        delta = (dt_close - dt_open).total_seconds()
        if delta > 0:
            deltas.append(delta)
    if not deltas:
        return None
    avg_sec = sum(deltas) / len(deltas)
    # Округляем до часов и минут.
    hours = int(avg_sec // 3600)
    minutes = int((avg_sec % 3600) // 60)
    if hours <= 0:
        return f"{minutes}м"
    return f"{hours}ч {minutes}м"


def _ai_gate_stats_for_symbol(
    symbol: str, days: int = 30, scan_limit: int = 500,
) -> dict[str, int]:
    """AI-Gate агрегация по конкретному символу: approve/veto/error/total.

    Делаем простой фильтр свежих записей gate-лога локально. Базовых
    хелперов хватает: get_ai_gate_recent уже даёт нам новейшие записи
    с пагинацией.
    """
    sym = str(symbol or "-").strip().upper()
    out = {"approve": 0, "veto": 0, "error": 0, "total": 0}
    try:
        recent = memory.get_ai_gate_recent(int(scan_limit))
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_ai_gate_recent: {exc}")
        return out
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
    for r in recent:
        if str(r.get("symbol") or "").upper() != sym:
            continue
        ts_dt = _parse_iso(str(r.get("ts") or ""))
        if ts_dt is not None and ts_dt < cutoff:
            continue
        verdict = str(r.get("verdict") or "").lower()
        if verdict in out:
            out[verdict] += 1
        out["total"] += 1
    return out


async def _handle_pair_detail(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    symbol: str,
) -> tuple[str, dict[str, Any]]:
    """Подробная карточка по символу: PF, средн. время, AI-Gate, top-loss."""
    sym = str(symbol or "-").strip().upper()
    if sym not in [s.upper() for s in config.SYMBOLS]:
        return await _handle_per_symbol_stats(session, state)

    try:
        stats = memory.get_symbol_stats_30d(sym)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_symbol_stats_30d({sym}): {exc}")
        stats = {
            "count": 0, "wins": 0, "losses": 0, "winrate": 0.0,
            "pnl_sum": 0.0, "avg_pnl": 0.0, "avg_rr_realized": 0.0,
        }
    try:
        recent = memory.get_last_trades(sym, 5)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_last_trades({sym}): {exc}")
        recent = []
    try:
        top_loss = memory.get_top_loss_reasons(sym, 30, 5)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_top_loss_reasons({sym}): {exc}")
        top_loss = []
    gate_stats = _ai_gate_stats_for_symbol(sym, days=30)

    # Profit factor: сумма выигрышей / |сумма проигрышей|. Сделки берём
    # из get_trades_since за 30 дней и фильтруем по символу.
    sum_wins = 0.0
    sum_losses_abs = 0.0
    try:
        trades = memory.get_trades_since(30)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_trades_since(30) for PF: {exc}")
        trades = []
    for t in trades:
        if str(t.get("symbol") or "").upper() != sym:
            continue
        outcome = str(t.get("outcome") or "").upper()
        try:
            pnl = float(t.get("pnl") or 0.0)
        except (TypeError, ValueError):
            pnl = 0.0
        if outcome == "WIN" and pnl > 0:
            sum_wins += pnl
        elif outcome == "LOSS" and pnl < 0:
            sum_losses_abs += abs(pnl)
    if sum_losses_abs > 0:
        pf_str = f"{sum_wins / sum_losses_abs:.2f}"
    elif sum_wins > 0:
        pf_str = "∞"
    else:
        pf_str = "-"

    avg_holding = _format_avg_holding(sym)

    count = int(stats.get("count") or 0)
    wins = int(stats.get("wins") or 0)
    losses = int(stats.get("losses") or 0)
    winrate = float(stats.get("winrate") or 0.0)
    pnl_sum = float(stats.get("pnl_sum") or 0.0)
    avg_pnl = float(stats.get("avg_pnl") or 0.0)
    dot = _pair_dot(count, winrate, pnl_sum)

    body: list[str] = [
        _label("Статус", f"{dot}  30 дней"),
        _subhr_line(),
        _label("Сделок", f"{count}  ({wins} win / {losses} loss)"),
        _label("Винрейт", f"{_fmt_num(winrate, 1)}%"),
        _label("PnL", _fmt_pnl(pnl_sum, 2)),
        _label("Средний", _fmt_pnl(avg_pnl, 2)),
        _label("Profit factor", pf_str),
    ]
    if avg_holding:
        body.append(_label("Среднее время", avg_holding))
    body.append(_subhr_line())

    body.append("Последние сделки:")
    if not recent:
        body.append("  (нет закрытых сделок)")
    else:
        for r in recent:
            outcome = str(r.get("outcome") or "-").upper()
            side = str(r.get("side") or "-")
            try:
                pnl = float(r.get("pnl") or 0.0)
            except (TypeError, ValueError):
                pnl = 0.0
            body.append(
                f"  {outcome:<4} {side:<5} {_fmt_pnl(pnl, 2)}"
            )

    body.append(_subhr_line())
    body.append("Топ причин убытков (rejected_checks):")
    if not top_loss:
        body.append("  (нет данных)")
    else:
        for r in top_loss:
            f_name = str(r.get("filter") or "-")
            cnt = int(r.get("count") or 0)
            body.append(f"  · {f_name} ({cnt})")

    body.append(_subhr_line())
    body.append("AI-Gate (30 дней):")
    body.append(
        f"  🟢 {gate_stats['approve']}  🔴 {gate_stats['veto']}  "
        f"🟡 {gate_stats['error']}  · {gate_stats['total']}"
    )

    text = _card(f"📈 {sym}", "", body)

    inline = {
        "inline_keyboard": [
            [{
                "text": "🚫 Заблокировать",
                "callback_data": f"{CB_PAIR_BLOCK_PREFIX}{sym}",
            }],
            [{"text": "◀ К таблице", "callback_data": CB_PAIRS}],
        ]
    }
    return text, inline


async def _handle_pair_block_start(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
    symbol: str,
) -> tuple[str, dict[str, Any]]:
    """Подготовить FSM из FEAT-004 на шаге `await_duration`, заполнив
    symbol заранее, и сразу показать выбор длительности — без необходимости
    повторно вводить тикер."""
    sym = str(symbol or "-").strip().upper()
    if not sym or not _looks_like_symbol(sym):
        return await _handle_per_symbol_stats(session, state)

    _blocks_fsm_state[chat_id] = {
        "step": "await_duration",
        "symbol": sym,
        "started": time.time(),
    }
    body = [
        _label("Пара", sym),
        _subhr_line(),
        "Выберите длительность блока:",
    ]
    duration_buttons: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for value, label in _BLOCKS_DURATIONS:
        row.append({
            "text": label,
            "callback_data": f"{CB_BLOCKS_DURATION_PREFIX}{value}",
        })
        if len(row) == 3:
            duration_buttons.append(row)
            row = []
    if row:
        duration_buttons.append(row)
    duration_buttons.append([{
        "text": "❌ Отмена",
        "callback_data": CB_BLOCKS_CANCEL,
    }])
    return _card("Добавить запрет", "🚫", body), {
        "inline_keyboard": duration_buttons,
    }


async def _handle_bt_stub(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Историческая заглушка кнопки 📉 Backtest (FEAT-008 / D).

    Сохранена ради совместимости старых ссылок в коде - реальный
    обработчик `_handle_backtest_menu` подключён ниже в диспетчере.
    """
    return _stage_placeholder("D (Backtest UI)")


# --- FEAT-008 / D: Backtest UI ----------------------------------------------
# Подменю «📉 Backtest» открывается из 📊 СТАТУС. Внутри:
#   1) переключатель периода 7д / 30д / 90д,
#   2) кнопка ▶ Запустить (синтетика, asyncio.to_thread, не блокирует loop),
#   3) после успеха карточка с метриками + сравнением с реальной торговлей,
#   4) кнопка 📥 CSV — отправка `backtest-Nd.csv` через send_document.
# Состояние per-chat (выбранный период, флаг «идёт расчёт», текст CSV)
# хранится в _bt_session_state. Один активный запуск на chat_id одновременно.
# Решение использовать ИСКЛЮЧИТЕЛЬНО синтетику (а не load_range) принято
# намеренно: load_range требует сети к Binance, что недопустимо в sandbox/
# offline-окружении. См. context.json: сделки против OKX/Binance отключены.

# Стартовые цены для генератора random_walk: реалистичные ориентиры по
# каждой паре, чтобы цифры в отчёте смотрелись правдоподобно.
_BT_DEFAULT_START_PRICES: dict[str, float] = {
    "BTCUSDT": 30000.0,
    "ETHUSDT": 2000.0,
    "SOLUSDT": 100.0,
    "BNBUSDT": 250.0,
    "XRPUSDT": 0.5,
    "DOGEUSDT": 0.07,
    "AVAXUSDT": 30.0,
}

_BT_PERIOD_OPTIONS: tuple[int, ...] = (7, 30, 90)
_BT_DEFAULT_PERIOD: int = 30

# Ограничители безопасности: даже 90д * 7 пар = 906_080 баров на пару
# никогда не должны полностью обрабатываться, поэтому сверху держим
# жёсткий лимит общего числа баров на запуск.
_BT_MAX_BARS_PER_SYMBOL: int = 90 * 24 * 60

# Per-chat сессия: {chat_id: {'period_days', 'running', 'csv_text'}}.
_bt_session_state: dict[int, dict[str, Any]] = {}


def _bt_get_session(chat_id: int) -> dict[str, Any]:
    """Вернуть (создать при отсутствии) bag-of-state для чата."""
    s = _bt_session_state.get(chat_id)
    if not isinstance(s, dict):
        s = {
            "period_days": _BT_DEFAULT_PERIOD,
            "running": False,
            "csv_text": None,
        }
        _bt_session_state[chat_id] = s
    return s


def _bt_period_label(days: int, current_days: int) -> str:
    """Текст кнопки периода с маркером ◀ возле выбранного."""
    base = f"{int(days)}д"
    return f"{base} ◀" if int(days) == int(current_days) else base


def _bt_metric_value(metrics: dict[str, Any], key: str) -> Optional[float]:
    raw = metrics.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) and raw == "inf":
        return float("inf")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _bt_format_pf(metrics: dict[str, Any]) -> str:
    pf = _bt_metric_value(metrics, "profit_factor")
    if pf is None:
        return "-"
    if pf == float("inf"):
        return "∞"
    return _fmt_num(pf, 2)


def _bt_compose_csv(closed_trades: list[dict[str, Any]]) -> str:
    """Собрать CSV-строку со списком закрытых сделок.

    Колонки: ts_open, ts_close, symbol, side, entry, exit, pnl, qty.
    ts_* выводятся в ISO8601 UTC, чтобы открывалось в любых табличках.
    """
    import csv as _csv  # локальный импорт - модуль нужен только здесь
    import io as _io

    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(
        ["ts_open", "ts_close", "symbol", "side", "entry", "exit", "pnl", "qty"]
    )
    for t in closed_trades or []:
        try:
            ts_open_ms = int(t.get("entry_ts") or 0)
            ts_close_ms = int(t.get("exit_ts") or 0)
        except (TypeError, ValueError):
            ts_open_ms = ts_close_ms = 0
        ts_open_iso = (
            datetime.fromtimestamp(ts_open_ms / 1000.0, tz=timezone.utc)
            .isoformat() if ts_open_ms > 0 else ""
        )
        ts_close_iso = (
            datetime.fromtimestamp(ts_close_ms / 1000.0, tz=timezone.utc)
            .isoformat() if ts_close_ms > 0 else ""
        )
        writer.writerow([
            ts_open_iso,
            ts_close_iso,
            str(t.get("symbol") or ""),
            str(t.get("side") or ""),
            f"{float(t.get('entry') or 0.0):.6f}",
            f"{float(t.get('exit') or 0.0):.6f}",
            f"{float(t.get('pnl') or 0.0):.6f}",
            f"{float(t.get('qty') or 0.0):.8f}",
        ])
    return buf.getvalue()


async def _run_backtest(period_days: int) -> dict[str, Any]:
    """Прогнать synthetic-бэктест за period_days по всем config.SYMBOLS.

    Запуск идёт через `asyncio.to_thread` (синхронный движок), чтобы не
    блокировать event-loop. Возвращает словарь с ключами:
        - metrics: dict (см. backtester.metrics.compute_metrics)
        - csv_text: str (CSV всех закрытых сделок)
        - period_days: int
        - symbols_count: int
    Любая ошибка пробрасывается наружу - вызов `_handle_backtest_run`
    оборачивает её в карточку.
    """
    # Локальные импорты, чтобы не утяжелять holod-импорт telegram_bot.
    import importlib

    import backtester.synthetic as bt_synth
    from backtester.config import (
        BacktesterConfig,
        DEFAULT_TICK_SIZE,
        HIGHER_TFS,
        PRIMARY_TF,
    )
    from backtester.engine import BacktestEngine
    from backtester.metrics import compute_metrics
    from backtester.portfolio import Portfolio

    period = max(1, int(period_days or _BT_DEFAULT_PERIOD))
    bars = min(period * 24 * 60, _BT_MAX_BARS_PER_SYMBOL)

    symbols = list(config.SYMBOLS)
    data_1m_by_symbol: dict[str, list[dict]] = {}
    for idx, sym in enumerate(symbols):
        start_price = _BT_DEFAULT_START_PRICES.get(sym, 1.0)
        data_1m_by_symbol[sym] = bt_synth.generate_random_walk(
            sym, bars, start_price=start_price, seed=42 + idx
        )

    bt_cfg = BacktesterConfig(initial_equity=10000.0)
    portfolio = Portfolio(10000.0, bt_cfg)
    strategy_mod = importlib.import_module("strategy_v2")
    primary_tf = getattr(bt_cfg, "primary_tf", None) or PRIMARY_TF
    engine = BacktestEngine(
        portfolio=portfolio,
        strategy_module=strategy_mod,
        symbols=symbols,
        primary_tf=primary_tf,
        higher_tfs=HIGHER_TFS,
        tick_sizes=DEFAULT_TICK_SIZE,
        config=bt_cfg,
    )

    def _runner() -> dict[str, Any]:
        result = engine.run(data_1m_by_symbol)
        # Метрика exposure_pct требует num_bars - выставляем ту же метку,
        # что делает backtester.run.main, чтобы цифры совпадали.
        try:
            portfolio._num_bars_seen = int(result.get("num_bars") or 0)
        except Exception:  # noqa: BLE001
            pass
        return result

    await asyncio.to_thread(_runner)

    metrics = compute_metrics(portfolio)
    csv_text = _bt_compose_csv(list(portfolio.closed_trades))

    return {
        "metrics": metrics,
        "csv_text": csv_text,
        "period_days": period,
        "symbols_count": len(symbols),
    }


def _bt_render_menu(chat_id: int) -> tuple[str, dict[str, Any]]:
    """Карточка меню backtest + inline-клавиатура.

    Используется и при первом открытии (`_handle_backtest_menu`), и при
    переключении периода (`_handle_backtest_period`) — чтобы маркер ◀
    «прыгал» между 7д/30д/90д.
    """
    sess = _bt_get_session(chat_id)
    period_days = int(sess.get("period_days") or _BT_DEFAULT_PERIOD)

    preset_key = _detect_current_preset()
    preset_label = (
        _AGGRESSIVENESS_LABELS.get(preset_key, "кастом")
        if preset_key else "кастом"
    )

    body = [
        _label("Период", f"{period_days}д"),
        _label("Символы", f"Все {len(config.SYMBOLS)}"),
        _label("Параметры", f"текущие · {preset_label}"),
        _subhr_line(),
        "⏱ Запуск займёт ~30с (синтетика).",
        "Реальные данные не используются —",
        "сетевые вызовы выключены в sandbox.",
    ]
    text = _card("Backtest", "📉", body)

    period_row = [
        {
            "text": _bt_period_label(d, period_days),
            "callback_data": f"{CB_BT_PERIOD_PREFIX}{d}",
        }
        for d in _BT_PERIOD_OPTIONS
    ]
    inline = {
        "inline_keyboard": [
            period_row,
            [{"text": "▶ Запустить", "callback_data": CB_BT_RUN}],
            [{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return text, inline


async def _handle_backtest_menu(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> tuple[str, dict[str, Any]]:
    """Открыть подменю Backtest c текущим выбранным периодом."""
    return _bt_render_menu(int(chat_id))


async def _handle_backtest_period(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
    period_str: str,
) -> tuple[str, dict[str, Any]]:
    """Переключить выбранный период (7/30/90д) и перерисовать меню."""
    sess = _bt_get_session(int(chat_id))
    try:
        period_days = int(period_str)
    except (TypeError, ValueError):
        period_days = _BT_DEFAULT_PERIOD
    if period_days not in _BT_PERIOD_OPTIONS:
        period_days = _BT_DEFAULT_PERIOD
    sess["period_days"] = period_days
    return _bt_render_menu(int(chat_id))


def _bt_render_report(
    *,
    period_days: int,
    symbols_count: int,
    metrics: dict[str, Any],
) -> str:
    """Сформировать карточку финального отчёта бэктеста."""
    today = datetime.now(tz=timezone.utc).date()
    start = today - timedelta(days=int(period_days))
    period_line = f"{start.isoformat()} → {today.isoformat()}"

    preset_key = _detect_current_preset()
    preset_label = (
        _AGGRESSIVENESS_LABELS.get(preset_key, "кастом")
        if preset_key else "кастом"
    )

    num_trades = int(metrics.get("num_trades") or 0)
    bt_winrate = _bt_metric_value(metrics, "win_rate_pct") or 0.0
    sharpe = _bt_metric_value(metrics, "sharpe") or 0.0
    mdd = _bt_metric_value(metrics, "max_drawdown_pct") or 0.0
    avg_win = _bt_metric_value(metrics, "avg_win") or 0.0
    avg_loss = _bt_metric_value(metrics, "avg_loss") or 0.0
    if num_trades > 0:
        avg_trade = (avg_win * (bt_winrate / 100.0)
                     + avg_loss * (1.0 - bt_winrate / 100.0))
    else:
        avg_trade = 0.0

    body: list[str] = [
        _label("Период", period_line),
        _label("Символы", f"Все {int(symbols_count)}"),
        _label("Параметры", f"текущие · {preset_label}"),
        _subhr_line(),
        "Метрики:",
        _label("  Сделок", _fmt_num(num_trades, 0)),
        _label("  Винрейт", f"{_fmt_num(bt_winrate, 1)}%"),
        _label("  Profit factor", _bt_format_pf(metrics)),
        _label("  Max DD", f"{_fmt_num(mdd, 2)}%"),
        _label("  Sharpe", _fmt_num(sharpe, 2)),
        _label("  Avg trade", _fmt_pnl(avg_trade, 2)),
        _subhr_line(),
        "Сравнение с реальной торговлей:",
    ]

    try:
        real_stats = memory.get_stats()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] backtest get_stats: {exc}")
        real_stats = {"count": 0, "winrate": 0.0}

    real_count = int(real_stats.get("count") or 0)
    if real_count <= 0 or num_trades <= 0:
        body.append("  Недостаточно данных для сравнения")
    else:
        real_wr = float(real_stats.get("winrate") or 0.0)
        delta = real_wr - bt_winrate
        if abs(delta) < 0.05:
            arrow = "·"
        elif delta > 0:
            arrow = "▲"
        else:
            arrow = "▼"
        sign = "+" if delta > 0 else ""
        body.append(_label(
            "  Винрейт реал",
            f"{_fmt_num(real_wr, 1)}%  {arrow} {sign}{_fmt_num(delta, 1)}",
        ))
        body.append(_label("  Сделок реал", _fmt_num(real_count, 0)))

    return _card("Backtest · отчёт", "📉", body)


async def _handle_backtest_run(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> Optional[str]:
    """Запуск бэктеста: «🔄 Идёт расчёт…» → editMessageText с отчётом.

    Возвращает None — диспетчер не шлёт дополнительное сообщение
    (мы уже обновили progress-сообщение через editMessageText).
    Если уже идёт расчёт — возвращает текстовую карточку «Уже идёт расчёт».
    """
    chat_id_int = int(chat_id)
    sess = _bt_get_session(chat_id_int)
    if sess.get("running"):
        return _card(
            "Backtest",
            "📉",
            ["Уже идёт расчёт. Подождите окончания и повторите."],
        )

    period_days = int(sess.get("period_days") or _BT_DEFAULT_PERIOD)
    sess["running"] = True

    # 1) Стартовая «карточка ожидания».
    progress_text = _card(
        "Backtest",
        "🔄",
        [
            f"Идёт расчёт за {period_days}д…",
            _subhr_line(),
            "Синтетические данные, ~30 секунд.",
        ],
    )
    sent = await send_message(session, progress_text, chat_id=chat_id_int)
    progress_msg_id: Optional[int] = None
    try:
        if sent and isinstance(sent, dict):
            progress_msg_id = int(((sent.get("result") or {}).get("message_id")) or 0) or None
    except (TypeError, ValueError):
        progress_msg_id = None

    # 2) Сам бэктест.
    try:
        result = await _run_backtest(period_days)
    except Exception as exc:  # noqa: BLE001
        sess["running"] = False
        err_text = _card(
            "Backtest · ошибка",
            "⚠️",
            [
                "Не удалось завершить расчёт.",
                _subhr_line(),
                _label("Причина", str(exc)[:200] or "неизвестна"),
            ],
        )
        if progress_msg_id is not None:
            ok = await edit_message_text(
                session, chat_id_int, progress_msg_id, err_text,
            )
            if ok:
                return None
        # Фоллбэк: если редактирование не получилось — отдаём как обычное
        # сообщение через диспетчер.
        return err_text

    # 3) Финальный отчёт.
    sess["csv_text"] = result.get("csv_text") or ""
    report_text = _bt_render_report(
        period_days=int(result.get("period_days") or period_days),
        symbols_count=int(result.get("symbols_count") or len(config.SYMBOLS)),
        metrics=dict(result.get("metrics") or {}),
    )
    report_keyboard = {
        "inline_keyboard": [
            [
                {"text": "📥 CSV", "callback_data": CB_BT_CSV},
                {"text": "◀ Назад", "callback_data": CB_BT_BACK},
            ]
        ]
    }
    if progress_msg_id is not None:
        ok = await edit_message_text(
            session,
            chat_id_int,
            progress_msg_id,
            report_text,
            reply_markup=report_keyboard,
        )
        if ok:
            sess["running"] = False
            return None
    # Фоллбэк: editMessageText не прошёл — шлём отчёт обычным сообщением.
    sess["running"] = False
    await send_message(
        session, report_text, reply_markup=report_keyboard, chat_id=chat_id_int,
    )
    return None


async def _handle_backtest_csv(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> Optional[str]:
    """Отправить CSV из последнего успешного запуска через send_document."""
    chat_id_int = int(chat_id)
    sess = _bt_get_session(chat_id_int)
    csv_text = sess.get("csv_text")
    if not csv_text:
        return _card(
            "Backtest · CSV",
            "📥",
            ["Сначала запустите backtest."],
        )
    period_days = int(sess.get("period_days") or _BT_DEFAULT_PERIOD)
    caption = _card(
        "Backtest CSV",
        "📥",
        [f"Сделки за {period_days}д сохранены в CSV."],
    )
    await send_document(
        session,
        str(csv_text).encode("utf-8"),
        filename=f"backtest-{period_days}d.csv",
        caption=caption,
        chat_id=chat_id_int,
    )
    return None


# --- FEAT-004 / B2: запретный список (manual + auto) ----------------------
# Подменю «🚫 Запреты» открывается из 📊 СТАТУС. Две секции:
#   - Заблокированы вручную (manual, 🔴) - снимает только пользователь;
#   - Заблокированы автоматически (auto, 🟡) - снимаются по таймеру или
#     первым WIN на символе (логика в main._check_closed_exchange_position).
# Добавление manual-блока через FSM: тикер -> длительность кнопками.
# Авто-настройки (streak / duration) меняются из подменю «⚙ Настройки
# авто-блока» через _write_env_var + setattr(config, ...).

# Варианты длительности при ручной блокировке. Кортежи (callback_value, текст_кнопки).
# Значение `inf` означает бессрочный блок (until_iso=NULL).
_BLOCKS_DURATIONS: list[tuple[str, str]] = [
    ("1", "1ч"),
    ("6", "6ч"),
    ("24", "24ч"),
    ("168", "7д"),
    ("inf", "Бессрочно"),
]

# Допустимые значения для подменю «Настройки авто-блока».
_BLOCKS_STREAK_OPTIONS: tuple[int, ...] = (2, 3, 5)
_BLOCKS_DURATION_OPTIONS: tuple[int, ...] = (6, 24, 72)

# Простая регулярка-проверка тикера (без import re, чтобы не плодить зависимости).
def _looks_like_symbol(value: str) -> bool:
    s = (value or "").strip().upper()
    if not s.endswith("USDT"):
        return False
    base = s[: -len("USDT")]
    if not base:
        return False
    return base.isalpha() and base.isascii()


def _blocks_fsm_clear(chat_id: int) -> None:
    _blocks_fsm_state.pop(chat_id, None)


def _blocks_fsm_expired(fsm: dict[str, Any]) -> bool:
    started = float(fsm.get("started") or 0.0)
    return time.time() - started > _BLOCKS_FSM_TIMEOUT_SEC


def _format_block_until(until_iso: Optional[str]) -> str:
    """Текстовое описание срока блока: '7ч 12м' или 'без срока'."""
    if not until_iso:
        return "без срока"
    dt = _parse_iso(until_iso)
    if dt is None:
        return "без срока"
    return _format_remaining(dt)


async def _handle_blocks_menu(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Подменю «🚫 Запреты» — manual + auto секции и доступные действия."""
    try:
        blocks = memory.list_active_blocks()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] list_active_blocks: {exc}")
        blocks = []

    manual_blocks = [b for b in blocks if str(b.get("type")) == "manual"]
    auto_blocks = [b for b in blocks if str(b.get("type")) == "auto"]

    body: list[str] = []
    inline_rows: list[list[dict[str, Any]]] = []

    # Manual.
    body.append("Заблокированы вручную:")
    if not manual_blocks:
        body.append("  (пусто)")
    else:
        for b in manual_blocks:
            sym = str(b.get("symbol") or "-")
            reason = str(b.get("reason") or "").strip()
            until_iso = b.get("until_iso")
            remaining = _format_block_until(until_iso)
            line = f"{_status_dot('bad')} {sym}  ({remaining})"
            if reason:
                line += f"  «{reason[:40]}»"
            body.append(line)
            inline_rows.append([{
                "text": f"Снять {sym}",
                "callback_data": f"{CB_BLOCKS_REMOVE_PREFIX}manual:{sym}",
            }])

    body.append(_subhr_line())

    # Auto.
    body.append("Заблокированы автоматически:")
    if not auto_blocks:
        body.append("  (пусто)")
    else:
        for b in auto_blocks:
            sym = str(b.get("symbol") or "-")
            reason = str(b.get("reason") or "").strip()
            until_iso = b.get("until_iso")
            remaining = _format_block_until(until_iso)
            line = f"{_status_dot('warn')} {sym}  ({remaining})"
            if reason:
                line += f"  «{reason[:40]}»"
            body.append(line)
            inline_rows.append([{
                "text": f"Снять {sym}",
                "callback_data": f"{CB_BLOCKS_REMOVE_PREFIX}auto:{sym}",
            }])

    body.append(_subhr_line())

    # Текущие настройки.
    try:
        streak = int(getattr(config, "AUTO_BLOCK_LOSS_STREAK", 3) or 3)
    except (TypeError, ValueError):
        streak = 3
    try:
        duration_h = int(getattr(config, "AUTO_BLOCK_DURATION_HOURS", 24) or 24)
    except (TypeError, ValueError):
        duration_h = 24
    body.append("Авто-блок:")
    body.append(_label("  N подряд LOSS", str(streak)))
    body.append(_label("  Длительность", f"{duration_h}ч"))

    text = _card("Запреты", "🚫", body)

    inline_rows.append([
        {"text": "➕ Добавить пару", "callback_data": CB_BLOCKS_ADD},
        {"text": "⚙ Настройки авто-блока",
         "callback_data": CB_BLOCKS_AUTOSETTINGS},
    ])
    inline_rows.append([{"text": "◀ Назад", "callback_data": CB_STATUS}])

    return text, {"inline_keyboard": inline_rows}


async def _handle_blocks_add_start(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> tuple[str, dict[str, Any]]:
    """Шаг 1 FSM: попросить пользователя ввести тикер."""
    _blocks_fsm_state[chat_id] = {
        "step": "await_symbol",
        "symbol": None,
        "started": time.time(),
    }
    body = [
        "Пришлите тикер пары одним сообщением.",
        _subhr_line(),
        "Например: XRPUSDT или BTCUSDT",
        "(только латиница, заканчивается на USDT).",
        _subhr_line(),
        "Время на ввод: 5 минут.",
    ]
    text = _card("Добавить запрет", "🚫", body)
    inline = {
        "inline_keyboard": [
            [{"text": "❌ Отмена", "callback_data": CB_BLOCKS_CANCEL}],
        ]
    }
    return text, inline


async def _handle_blocks_cancel(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> tuple[str, dict[str, Any]]:
    """Отмена FSM добавления блока: чистим состояние, возврат в подменю."""
    _blocks_fsm_clear(chat_id)
    return await _handle_blocks_menu(session, state)


async def _handle_blocks_duration_pick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
    duration_value: str,
) -> tuple[str, dict[str, Any]]:
    """Шаг 2 FSM: выбрана длительность, ставим manual-блок."""
    fsm = _blocks_fsm_state.get(chat_id)
    if not fsm or fsm.get("step") != "await_duration":
        return await _handle_blocks_menu(session, state)
    if _blocks_fsm_expired(fsm):
        _blocks_fsm_clear(chat_id)
        return (
            _card(
                "Запреты",
                "🚫",
                ["Сессия добавления блока истекла (5 минут).",
                 "Начните заново."],
            ),
            {"inline_keyboard": [[
                {"text": "◀ Назад", "callback_data": CB_BLOCKS},
            ]]},
        )
    symbol = str(fsm.get("symbol") or "").upper()
    if not symbol:
        _blocks_fsm_clear(chat_id)
        return await _handle_blocks_menu(session, state)

    until_iso: Optional[str]
    if duration_value == "inf":
        until_iso = None
    else:
        try:
            hours = int(duration_value)
        except (TypeError, ValueError):
            hours = 24
        until_dt = datetime.now(tz=timezone.utc) + timedelta(hours=hours)
        until_iso = until_dt.isoformat(timespec="seconds")

    try:
        memory.add_symbol_block(symbol, "manual", until_iso, "ручная блокировка")
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] add_symbol_block({symbol}): {exc}")
        _blocks_fsm_clear(chat_id)
        return (
            _card(
                "Запреты",
                "🚫",
                [f"Не удалось добавить блок: {exc}"],
            ),
            {"inline_keyboard": [[
                {"text": "◀ Назад", "callback_data": CB_BLOCKS},
            ]]},
        )
    _blocks_fsm_clear(chat_id)
    return await _handle_blocks_menu(session, state)


async def _handle_blocks_remove(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    target: str,
) -> tuple[str, dict[str, Any]]:
    """Снять блок по '<type>:<symbol>' (manual:XRPUSDT, auto:BTCUSDT и т.п.)."""
    try:
        block_type, symbol = target.split(":", 1)
    except ValueError:
        return await _handle_blocks_menu(session, state)
    block_type = block_type.strip().lower()
    symbol = symbol.strip().upper()
    if block_type not in ("manual", "auto") or not symbol:
        return await _handle_blocks_menu(session, state)
    try:
        memory.remove_symbol_block(symbol, type=block_type)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] remove_symbol_block({symbol}, {block_type}): {exc}")
    return await _handle_blocks_menu(session, state)


async def _handle_blocks_autosettings(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Подменю «⚙ Настройки авто-блока»."""
    try:
        cur_streak = int(getattr(config, "AUTO_BLOCK_LOSS_STREAK", 3) or 3)
    except (TypeError, ValueError):
        cur_streak = 3
    try:
        cur_hours = int(getattr(config, "AUTO_BLOCK_DURATION_HOURS", 24) or 24)
    except (TypeError, ValueError):
        cur_hours = 24

    body: list[str] = [
        "N подряд LOSS до авто-блока:",
        _label("  Сейчас", str(cur_streak)),
        _subhr_line(),
        "Длительность авто-блока:",
        _label("  Сейчас", f"{cur_hours}ч"),
        _subhr_line(),
        "Изменения сохраняются в .env",
        "и применяются сразу (без рестарта).",
    ]
    text = _card("Настройки авто-блока", "⚙", body)

    streak_row: list[dict[str, Any]] = []
    for opt in _BLOCKS_STREAK_OPTIONS:
        label = f"{opt}"
        if opt == cur_streak:
            label = f"{label} ◀"
        streak_row.append({
            "text": label,
            "callback_data": f"{CB_BLOCKS_AUTOSET_PREFIX}s:{opt}",
        })
    duration_row: list[dict[str, Any]] = []
    for opt in _BLOCKS_DURATION_OPTIONS:
        label = f"{opt}ч"
        if opt == cur_hours:
            label = f"{label} ◀"
        duration_row.append({
            "text": label,
            "callback_data": f"{CB_BLOCKS_AUTOSET_PREFIX}h:{opt}",
        })
    inline = {
        "inline_keyboard": [
            [{"text": "Серия LOSS:", "callback_data": CB_BLOCKS_AUTOSETTINGS}],
            streak_row,
            [{"text": "Длительность:", "callback_data": CB_BLOCKS_AUTOSETTINGS}],
            duration_row,
            [{"text": "◀ К списку запретов", "callback_data": CB_BLOCKS}],
        ]
    }
    return text, inline


async def _handle_blocks_autoset(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    payload: str,
) -> tuple[str, dict[str, Any]]:
    """Применить выбранное значение авто-настройки. payload = '<field>:<value>'."""
    try:
        field, value = payload.split(":", 1)
    except ValueError:
        return await _handle_blocks_autosettings(session, state)
    field = field.strip().lower()
    try:
        value_int = int(value)
    except (TypeError, ValueError):
        return await _handle_blocks_autosettings(session, state)

    if field == "s":
        if value_int not in _BLOCKS_STREAK_OPTIONS:
            return await _handle_blocks_autosettings(session, state)
        env_name = "AUTO_BLOCK_LOSS_STREAK"
        attr_name = "AUTO_BLOCK_LOSS_STREAK"
    elif field == "h":
        if value_int not in _BLOCKS_DURATION_OPTIONS:
            return await _handle_blocks_autosettings(session, state)
        env_name = "AUTO_BLOCK_DURATION_HOURS"
        attr_name = "AUTO_BLOCK_DURATION_HOURS"
    else:
        return await _handle_blocks_autosettings(session, state)

    if not _write_env_var(env_name, str(value_int)):
        return (
            _card(
                "Настройки авто-блока",
                "⚙",
                [f"Не удалось записать {env_name} в .env"],
            ),
            {"inline_keyboard": [[
                {"text": "◀ Назад", "callback_data": CB_BLOCKS_AUTOSETTINGS},
            ]]},
        )
    setattr(config, attr_name, int(value_int))
    return await _handle_blocks_autosettings(session, state)


# --- Конец FEAT-004 -------------------------------------------------------


# --- FEAT-003 / B1: слайдер агрессивности торговли -------------------------
# Три пресета атомарно записывают 6 параметров в .env и применяют их в
# памяти через setattr(config, ...). AI_TRADE_GATE_MODE остаётся "active"
# во всех пресетах (требование владельца — без shadow на 7-14 дней).
# Per-symbol MIN_ATR_PCT (config.MIN_ATR_PCT) НЕ трогается — пресеты влияют
# только на дефолт MIN_ATR_PCT_DEFAULT.

_AGGR_FLOAT_TOL = 1e-6  # допуск для сравнения live-значений с пресетом

_AGGRESSIVENESS_PRESETS: dict[str, dict[str, Any]] = {
    "conservative": {
        "RISK_PER_TRADE": 0.005,
        "GLOBAL_RISK_CAP": 0.02,
        "MIN_ATR_PCT_DEFAULT": 0.0045,
        "MAX_DAILY_LOSS": 0.02,
        "MAX_WEEKLY_LOSS": 0.05,
        "AI_TRADE_GATE_MODE": "active",
    },
    "medium": {
        "RISK_PER_TRADE": 0.01,
        "GLOBAL_RISK_CAP": 0.04,
        "MIN_ATR_PCT_DEFAULT": 0.003,
        "MAX_DAILY_LOSS": 0.03,
        "MAX_WEEKLY_LOSS": 0.07,
        "AI_TRADE_GATE_MODE": "active",
    },
    "aggressive": {
        "RISK_PER_TRADE": 0.015,
        "GLOBAL_RISK_CAP": 0.06,
        "MIN_ATR_PCT_DEFAULT": 0.0024,
        "MAX_DAILY_LOSS": 0.04,
        "MAX_WEEKLY_LOSS": 0.09,
        "AI_TRADE_GATE_MODE": "active",
    },
}

_AGGRESSIVENESS_LABELS: dict[str, str] = {
    "conservative": "🐢 Консервативно",
    "medium": "⚡ Средне",
    "aggressive": "🔥 Агрессивно",
}

# Порядок отображения пресетов в подменю.
_AGGRESSIVENESS_ORDER: list[str] = ["conservative", "medium", "aggressive"]

# Список «риск»-параметров (числовых, float).
_AGGRESSIVENESS_FLOAT_KEYS: tuple[str, ...] = (
    "RISK_PER_TRADE",
    "GLOBAL_RISK_CAP",
    "MIN_ATR_PCT_DEFAULT",
    "MAX_DAILY_LOSS",
    "MAX_WEEKLY_LOSS",
)


def _detect_current_preset() -> Optional[str]:
    """Определить текущий пресет по живым значениям config.*.

    Сравнение float — с допуском ±1e-6. AI_TRADE_GATE_MODE сравнивается
    как нижний регистр строки. Возвращает ключ ('conservative'|'medium'|
    'aggressive') или None если ни один пресет не совпал.
    """
    live_gate = str(
        getattr(config, "AI_TRADE_GATE_MODE", "") or ""
    ).strip().lower()
    live_floats: dict[str, Any] = {}
    for key in _AGGRESSIVENESS_FLOAT_KEYS:
        try:
            live_floats[key] = float(getattr(config, key))
        except (TypeError, ValueError, AttributeError):
            return None

    for preset_key in _AGGRESSIVENESS_ORDER:
        preset = _AGGRESSIVENESS_PRESETS[preset_key]
        if str(preset["AI_TRADE_GATE_MODE"]).lower() != live_gate:
            continue
        match = True
        for fk in _AGGRESSIVENESS_FLOAT_KEYS:
            if abs(live_floats[fk] - float(preset[fk])) > _AGGR_FLOAT_TOL:
                match = False
                break
        if match:
            return preset_key
    return None


def _aggr_preset_summary_lines(preset_key: str) -> list[str]:
    """Краткое описание параметров пресета — табличные строки."""
    p = _AGGRESSIVENESS_PRESETS[preset_key]
    return [
        _label("Риск/сделка", _fmt_pct(float(p["RISK_PER_TRADE"]) * 100.0, 2)),
        _label("Сум. риск", _fmt_pct(float(p["GLOBAL_RISK_CAP"]) * 100.0, 2)),
        _label("ATR мин.",
               _fmt_pct(float(p["MIN_ATR_PCT_DEFAULT"]) * 100.0, 2)),
        _label("Дневн. стоп",
               _fmt_pct(float(p["MAX_DAILY_LOSS"]) * 100.0, 2)),
        _label("Недельн. стоп",
               _fmt_pct(float(p["MAX_WEEKLY_LOSS"]) * 100.0, 2)),
        _label("AI-Gate", str(p["AI_TRADE_GATE_MODE"])),
    ]


def _aggr_live_summary_lines() -> list[str]:
    """Текущие значения config.* в том же формате, что и summary пресета."""
    try:
        risk = float(getattr(config, "RISK_PER_TRADE", 0.0))
    except (TypeError, ValueError):
        risk = 0.0
    try:
        cap = float(getattr(config, "GLOBAL_RISK_CAP", 0.0))
    except (TypeError, ValueError):
        cap = 0.0
    try:
        atr_def = float(getattr(config, "MIN_ATR_PCT_DEFAULT", 0.0))
    except (TypeError, ValueError):
        atr_def = 0.0
    try:
        d_loss = float(getattr(config, "MAX_DAILY_LOSS", 0.0))
    except (TypeError, ValueError):
        d_loss = 0.0
    try:
        w_loss = float(getattr(config, "MAX_WEEKLY_LOSS", 0.0))
    except (TypeError, ValueError):
        w_loss = 0.0
    gate = str(
        getattr(config, "AI_TRADE_GATE_MODE", "") or ""
    ).strip().lower() or "-"
    return [
        _label("Риск/сделка", _fmt_pct(risk * 100.0, 2)),
        _label("Сум. риск", _fmt_pct(cap * 100.0, 2)),
        _label("ATR мин.", _fmt_pct(atr_def * 100.0, 2)),
        _label("Дневн. стоп", _fmt_pct(d_loss * 100.0, 2)),
        _label("Недельн. стоп", _fmt_pct(w_loss * 100.0, 2)),
        _label("AI-Gate", gate),
    ]


def _apply_aggressiveness_preset(preset_key: str) -> tuple[bool, str]:
    """Атомарно записать 6 ключей в .env и применить через setattr(config).

    При сбое любого `_write_env_var` — откатывает уже применённые setattr
    к предыдущим значениям и возвращает (False, причина). Возвращает
    (True, preset_key) при успехе.
    """
    if preset_key not in _AGGRESSIVENESS_PRESETS:
        return False, f"Неизвестный пресет: {preset_key!r}"
    preset = _AGGRESSIVENESS_PRESETS[preset_key]

    # Сохраняем предыдущие живые значения для возможного отката.
    snapshot: dict[str, Any] = {}
    for name in preset.keys():
        snapshot[name] = getattr(config, name, None)

    applied: list[str] = []  # имена, которые уже успели записать в .env
    try:
        for name, value in preset.items():
            str_value = str(value)
            if not _write_env_var(name, str_value):
                # Откатить уже записанные .env-ключи и setattr.
                for prev_name in applied:
                    prev_val = snapshot.get(prev_name)
                    try:
                        # Возвращаем .env к прежнему значению.
                        if prev_val is None:
                            _write_env_var(prev_name, "")
                        else:
                            _write_env_var(prev_name, str(prev_val))
                    except Exception as exc:  # noqa: BLE001
                        print(
                            f"[TG] _apply_aggressiveness_preset: "
                            f"ошибка отката .env {prev_name}: {exc}"
                        )
                    try:
                        setattr(config, prev_name, prev_val)
                    except Exception as exc:  # noqa: BLE001
                        print(
                            f"[TG] _apply_aggressiveness_preset: "
                            f"ошибка отката setattr {prev_name}: {exc}"
                        )
                return False, f"Не удалось записать .env: {name}"
            applied.append(name)
            # Применяем in-memory сразу — с правильным типом.
            if name == "AI_TRADE_GATE_MODE":
                setattr(config, name, str(value))
            else:
                setattr(config, name, float(value))
        return True, preset_key
    except Exception as exc:  # noqa: BLE001
        # На случай неожиданной ошибки — попытка отката.
        for prev_name, prev_val in snapshot.items():
            try:
                setattr(config, prev_name, prev_val)
            except Exception:  # noqa: BLE001
                pass
        return False, f"Внутренняя ошибка: {exc}"


async def _handle_aggressiveness_menu(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Подменю «🎚 Агрессивность торговли» — выбор пресета."""
    current = _detect_current_preset()

    if current is None:
        current_block: list[str] = [
            _label("Сейчас", "Кастомные настройки"),
            _subhr_line(),
            "Текущие значения:",
        ]
        current_block.extend("  " + line for line in _aggr_live_summary_lines())
    else:
        current_block = [
            _label("Сейчас", _AGGRESSIVENESS_LABELS[current]),
        ]

    body: list[str] = list(current_block)
    body.append(_subhr_line())
    body.append("Выберите пресет:")

    for key in _AGGRESSIVENESS_ORDER:
        body.append("")
        suffix = "  ◀ сейчас" if key == current else ""
        body.append(f"{_AGGRESSIVENESS_LABELS[key]}{suffix}")
        body.extend("  " + line for line in _aggr_preset_summary_lines(key))

    body.append(_subhr_line())
    body.append("Применение атомарное: 6 параметров в .env")
    body.append("и в памяти без рестарта.")
    body.append("Открытые позиции продолжают работать")
    body.append("по своим параметрам (изменения — для новых).")

    text = _card("Агрессивность торговли", "🎚", body)

    inline_rows: list[list[dict[str, Any]]] = []
    for key in _AGGRESSIVENESS_ORDER:
        label = _AGGRESSIVENESS_LABELS[key]
        if key == current:
            label = f"{label} ◀ сейчас"
        inline_rows.append(
            [{"text": label, "callback_data": f"{CB_AGGR_SET_PREFIX}{key}"}]
        )
    inline_rows.append([{"text": "◀ Назад", "callback_data": CB_STATUS}])
    return text, {"inline_keyboard": inline_rows}


async def _handle_aggressiveness_confirm(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    preset_key: str,
) -> tuple[str, dict[str, Any]]:
    """Шаг 2: подтверждение применения пресета."""
    if preset_key not in _AGGRESSIVENESS_PRESETS:
        return (
            _card("Агрессивность", "🎚", [f"Неизвестный пресет: {preset_key}"]),
            {"inline_keyboard": [[
                {"text": "◀ Назад", "callback_data": CB_AGGR_MENU},
            ]]},
        )

    current = _detect_current_preset()
    current_pretty = (
        _AGGRESSIVENESS_LABELS[current] if current else "Кастомные настройки"
    )
    target_pretty = _AGGRESSIVENESS_LABELS[preset_key]

    body: list[str] = [
        _label("Сейчас", current_pretty),
        _label("Станет", target_pretty),
        _subhr_line(),
        "Параметры пресета:",
    ]
    body.extend("  " + line for line in _aggr_preset_summary_lines(preset_key))
    body.append(_subhr_line())
    body.append("Открытые позиции остаются на старых")
    body.append("параметрах — изменения применятся к новым.")
    body.append("Подтвердить?")

    text = _card("Применить пресет", "🎚", body)
    inline = {
        "inline_keyboard": [
            [
                {"text": "✅ Да, применить",
                 "callback_data": f"{CB_AGGR_CONFIRM_PREFIX}{preset_key}"},
                {"text": "❌ Отмена", "callback_data": CB_AGGR_MENU},
            ],
        ]
    }
    return text, inline


async def _handle_aggressiveness_apply(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    preset_key: str,
) -> tuple[str, dict[str, Any]]:
    """Шаг 3: применение пресета (.env + setattr in-memory)."""
    if preset_key not in _AGGRESSIVENESS_PRESETS:
        return (
            _card("Агрессивность", "🎚", [f"Неизвестный пресет: {preset_key}"]),
            {"inline_keyboard": [[
                {"text": "◀ Назад", "callback_data": CB_AGGR_MENU},
            ]]},
        )

    ok, result = _apply_aggressiveness_preset(preset_key)
    if not ok:
        body = [
            "Не удалось применить пресет.",
            _label("Причина", str(result)),
            _subhr_line(),
            "Изменения откачены.",
        ]
        return (
            _card("Ошибка применения", "🎚", body),
            {"inline_keyboard": [[
                {"text": "◀ Назад", "callback_data": CB_AGGR_MENU},
            ]]},
        )

    pretty = _AGGRESSIVENESS_LABELS[preset_key]
    body = [
        _label("Пресет", pretty),
        _subhr_line(),
        "Новые значения:",
    ]
    body.extend("  " + line for line in _aggr_live_summary_lines())
    body.append(_subhr_line())
    body.append("Сохранено в .env, применено в памяти.")
    body.append("Открытые позиции продолжаются по")
    body.append("своим параметрам — изменения для новых.")
    text = _card("Применён пресет", "🎚", body)
    inline = {
        "inline_keyboard": [
            [{"text": "◀ В подменю", "callback_data": CB_AGGR_MENU}],
            [{"text": "🏠 Главное меню", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return text, inline


# --- Обработчики кнопок главного меню --------------------------------------

async def _handle_status(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    g = _g(state)
    stats = memory.get_stats()
    equity_start = float(g.get("equity_start") or 0.0)
    cumulative_pnl = float(g.get("cumulative_pnl", 0.0) or 0.0)
    equity_now = equity_start + cumulative_pnl
    pct_from_start = (
        (cumulative_pnl / equity_start * 100.0) if equity_start > 0 else 0.0
    )

    # Открытые позиции (по state).
    open_cnt = sum(
        1 for s in state.get("symbols", {}).values() if s.get("open_trade")
    )
    total_cnt = len(config.SYMBOLS)

    # Режимы: две строки для 7 символов (4 + 3). Каждый символ — `dot SYM`
    # с обрезанием хвоста USDT для компактности (BTCUSDT → BTC).
    regime_blocks: list[str] = []
    for symbol in config.SYMBOLS:
        sym_state = (state.get("symbols") or {}).get(symbol) or {}
        regime = sym_state.get("regime") or {}
        emoji = _regime_emoji(regime.get("regime") or "")
        short_sym = symbol.replace("USDT", "")
        regime_blocks.append(f"{emoji} {short_sym}")
    row1 = "  ".join(regime_blocks[:4])
    row2 = "  ".join(regime_blocks[4:])

    # AI-Gate статистика.
    try:
        gate_stats = memory.get_ai_gate_stats(24)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] ошибка get_ai_gate_stats: {exc}")
        gate_stats = {"approve": 0, "veto": 0, "error": 0, "total": 0, "applied": 0}
    gate_mode_raw = str(
        getattr(config, "AI_TRADE_GATE_MODE", "off") or "off"
    ).lower()
    gate_mode_ru = {
        "active": "активен",
        "shadow": "наблюдение",
        "off": "выключен",
    }.get(gate_mode_raw, gate_mode_raw)
    gate_dot = _status_dot({
        "active": "ok",
        "shadow": "warn",
        "off": "off",
    }.get(gate_mode_raw, "off"))

    dry_run_on = bool(getattr(config, "DRY_RUN", False))
    dry_run_label = "ВКЛ" if dry_run_on else "ВЫКЛ"
    dry_dot = _status_dot("warn" if dry_run_on else "ok")

    is_demo = bool(config.IS_TESTNET)
    mode_label = "ДЕМО (OKX testnet)" if is_demo else "РЕАЛ (OKX mainnet)"
    mode_dot = _status_dot("ok" if is_demo else "bad")

    kill_state = str(g.get("kill_switch_state") or "NONE")
    kill_until_iso = g.get("kill_until_utc")
    if kill_state != "NONE" and kill_until_iso:
        kill_line = f"{kill_state} (до {kill_until_iso})"
    elif kill_state != "NONE":
        kill_line = f"{kill_state} (без срока)"
    else:
        kill_line = "NONE"
    kill_dot = _status_dot("bad" if kill_state != "NONE" else "ok")

    started_epoch = float(g.get("started_epoch") or 0.0)
    uptime = _format_uptime(time.time() - started_epoch) if started_epoch else "-"

    bot_running = bool(g.get("bot_running", True))
    bot_dot = _status_dot("ok" if bot_running else "bad")
    bot_label = "запущен" if bot_running else "на паузе"

    winrate = float(stats.get("winrate") or 0.0)

    body: list[str] = [
        _label("Баланс", f"{_fmt_num(equity_now, 2)} USDT"),
        _label("От старта", _fmt_pct(pct_from_start, 2)),
        _subhr_line(),
        _label("Сделки", f"{int(stats.get('count') or 0)}"),
        _label("Винрейт", f"{_fmt_num(winrate, 1)}%"),
        _label("Открыто", f"{open_cnt} / {total_cnt}"),
        _subhr_line(),
        "Режимы:",
        f"  {row1}",
    ]
    if row2:
        body.append(f"  {row2}")
    body.append(_subhr_line())
    body.append(_label("AI-Gate", f"{gate_dot} {gate_mode_ru}"))
    body.append(
        f"  24ч: 🟢 {gate_stats['approve']}  🔴 {gate_stats['veto']}  "
        f"🟡 {gate_stats['error']}  · {gate_stats['total']}"
    )
    body.append(_subhr_line())
    body.append(_label("DRY_RUN", f"{dry_dot} {dry_run_label}"))
    body.append(_label("Режим", f"{mode_dot} {mode_label}"))
    body.append(_label("Kill", f"{kill_dot} {kill_line}"))
    body.append(_label("Uptime", uptime))
    body.append(_label("Торговля", f"{bot_dot} {bot_label}"))

    text = _card("Статус", "📊", body)

    # Кнопка агрессивности — детектируем текущий пресет по живым значениям
    # config.* и показываем его метку. Если ни один пресет не совпал —
    # «кастом» (FEAT-003).
    aggr_current = _detect_current_preset()
    aggr_lvl_ru = _AGGRESSIVENESS_LABELS.get(aggr_current, "кастом")

    inline: list[list[dict[str, Any]]] = [
        [
            {"text": f"🎚 Агрессивность: {aggr_lvl_ru}",
             "callback_data": CB_AGGR_MENU},
            {"text": "🧪 DRY_RUN", "callback_data": CB_TOGGLE_DRY_RUN},
        ],
        [
            {"text": "🤖 AI-Gate", "callback_data": CB_AIGATE_MENU},
            {"text": "🏦 Демо/Реал", "callback_data": CB_MODE_SWITCH},
        ],
        [
            {"text": "🚫 Запреты", "callback_data": CB_BLOCKS},
            {"text": "📈 По парам", "callback_data": CB_PAIRS},
        ],
        [
            {"text": "📉 Backtest", "callback_data": CB_BT_MENU},
            {"text": "🤖 GROQ", "callback_data": CB_GROQ},
        ],
    ]
    if kill_state != "NONE":
        inline.append(
            [{"text": "🆘 Снять kill-switch", "callback_data": CB_KILL_CLEAR}]
        )
    inline.append([{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}])

    return text, {"inline_keyboard": inline}


async def _handle_positions(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Список открытых позиций с подтягиванием свежих цен через API."""
    positions: list[dict[str, Any]] = []
    for symbol in config.SYMBOLS:
        sym_state = (state.get("symbols") or {}).get(symbol) or {}
        trade = sym_state.get("open_trade")
        if not trade:
            continue
        side = str(trade.get("side") or "")
        entry = float(trade.get("entry_price") or 0.0)
        qty = float(trade.get("qty") or 0.0)
        stop = float(trade.get("current_stop") or 0.0)
        entry_ts_iso = trade.get("entry_ts_iso") or ""

        # Текущая цена - через get_klines(1m).
        cur_price = entry
        try:
            klines = await EXCHANGE.get_klines(session, symbol, "1", 1)
            if klines:
                cur_price = float(klines[-1][4])
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] get_klines({symbol}) для ПОЗИЦИИ: {exc}")

        if side == "Buy":
            pnl_abs = (cur_price - entry) * qty
            pnl_pct = (
                ((cur_price - entry) / entry) * 100.0 if entry > 0 else 0.0
            )
            stop_pct = (
                ((entry - stop) / entry) * -100.0 if entry > 0 else 0.0
            )
        else:
            pnl_abs = (entry - cur_price) * qty
            pnl_pct = (
                ((entry - cur_price) / entry) * 100.0 if entry > 0 else 0.0
            )
            stop_pct = (
                ((stop - entry) / entry) * 100.0 if entry > 0 else 0.0
            )

        positions.append({
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "cur": cur_price,
            "qty": qty,
            "stop": stop,
            "pnl_abs": pnl_abs,
            "pnl_pct": pnl_pct,
            "stop_pct": stop_pct,
            "entry_ts_iso": entry_ts_iso,
        })

    if not positions:
        return _card("Позиции", "📈", ["Нет открытых позиций"])

    # Сортировка по PnL abs по убыванию.
    positions.sort(key=lambda p: p["pnl_abs"], reverse=True)

    now = datetime.now(tz=timezone.utc)
    body: list[str] = []
    for idx, p in enumerate(positions):
        if idx > 0:
            body.append(_subhr_line())
        side_label = "LONG" if p["side"] == "Buy" else "SHORT"
        # Точечный индикатор по знаку PnL.
        if p["pnl_abs"] > 0:
            dot = _status_dot("ok")
        elif p["pnl_abs"] < 0:
            dot = _status_dot("bad")
        else:
            dot = _status_dot("warn")
        entry_ts = _parse_iso(p["entry_ts_iso"])
        hold = (
            _format_uptime((now - entry_ts).total_seconds())
            if entry_ts else "-"
        )
        body.append(f"{dot} {p['symbol']}  {_dir_arrow(side_label)}")
        body.append(_label("  Вход", _fmt_num(p["entry"], 4)))
        body.append(_label("  Сейчас", _fmt_num(p["cur"], 4)))
        body.append(_label("  PnL", f"{_fmt_pnl(p['pnl_abs'], 2)} USDT"))
        body.append(_label("  PnL %", _fmt_pct(p["pnl_pct"], 2)))
        body.append(_label("  Время", hold))
        body.append(_label(
            "  Стоп",
            f"{_fmt_num(p['stop'], 4)}  ({_fmt_pct(p['stop_pct'], 2)})",
        ))
    return _card("Позиции", "📈", body)


async def _handle_regimes(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Режимы рынка по 7 символам + последнее обновление."""
    body: list[str] = []
    last_ts: Optional[datetime] = None
    for symbol in config.SYMBOLS:
        sym_state = (state.get("symbols") or {}).get(symbol) or {}
        regime = sym_state.get("regime") or {}
        r_name = str(regime.get("regime") or "-")
        conf = regime.get("confidence")
        reason = str(regime.get("reason") or "").strip()
        if len(reason) > 60:
            reason = reason[:57] + "..."
        ts = _parse_iso(regime.get("ts"))
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts
        # Точечный индикатор: тренд = ok, боковик = warn, кризис = bad.
        r_up = r_name.upper()
        dot = _status_dot({
            "TRENDING": "ok",
            "RANGING": "warn",
            "CRISIS": "bad",
        }.get(r_up, "off"))
        conf_str = f"{int(conf)}" if conf is not None else "?"
        body.append(
            f"{dot} {symbol}  {_ru_regime(r_name)}  conf={conf_str}"
        )
        if reason:
            body.append(f"  «{reason}»")
    if last_ts:
        body.append(_subhr_line())
        body.append(_label("Обновлено", last_ts.strftime("%H:%M UTC")))
    return _card("Режимы", "🎯", body)


async def _handle_aigate(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Меню AI-Gate: статус + статистика 24ч/7д + топ причин + inline-действия."""
    gate_mode_raw = str(
        getattr(config, "AI_TRADE_GATE_MODE", "off") or "off"
    ).lower()
    gate_mode_ru = {
        "active": "активен",
        "shadow": "наблюдение",
        "off": "выключен",
    }.get(gate_mode_raw, gate_mode_raw)
    gate_dot = _status_dot({
        "active": "ok",
        "shadow": "warn",
        "off": "off",
    }.get(gate_mode_raw, "off"))

    try:
        stats24 = memory.get_ai_gate_stats(24)
        stats7d = memory.get_ai_gate_stats(24 * 7)
        top_reasons = memory.get_ai_gate_top_veto_reasons(24 * 7, limit=5)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] AI-Gate stats ошибка: {exc}")
        stats24 = {"approve": 0, "veto": 0, "error": 0, "total": 0, "applied": 0}
        stats7d = dict(stats24)
        top_reasons = []

    body: list[str] = [
        _label("Режим", f"{gate_dot} {gate_mode_ru}"),
        _subhr_line(),
        "За 24 часа:",
        _label("  Одобрено", f"{stats24['approve']}"),
        _label("  Veto", f"{stats24['veto']}"),
        _label("  Ошибка", f"{stats24['error']}"),
        _label("  Всего", f"{stats24['total']}"),
        _subhr_line(),
        "За 7 дней:",
        f"  🟢 {stats7d['approve']}  🔴 {stats7d['veto']}  🟡 {stats7d['error']}",
        _subhr_line(),
        "Топ причин блокировки (7 дней):",
    ]
    if top_reasons:
        for i, r in enumerate(top_reasons, start=1):
            reason = str(r.get("reason") or "-")
            if len(reason) > 60:
                reason = reason[:57] + "..."
            body.append(f"  {i}. {reason} ({r['count']})")
    else:
        body.append("  (блокировок за 7 дней нет)")

    text = _card("AI-Gate", "🛡", body)

    # Inline-кнопки: адаптивно под текущий режим. Лаконичные ASCII-метки.
    inline: list[list[dict[str, Any]]] = []
    if gate_mode_raw == "active":
        inline.append([
            {"text": "Перейти в наблюдение",
             "callback_data": CB_AIGATE_SET_SHADOW},
        ])
        inline.append([
            {"text": "Выключить",
             "callback_data": CB_AIGATE_SET_OFF},
        ])
    elif gate_mode_raw == "shadow":
        inline.append([
            {"text": "Включить active",
             "callback_data": CB_AIGATE_SET_ACTIVE},
        ])
        inline.append([
            {"text": "Выключить",
             "callback_data": CB_AIGATE_SET_OFF},
        ])
    else:  # off
        inline.append([
            {"text": "Включить active",
             "callback_data": CB_AIGATE_SET_ACTIVE},
        ])
        inline.append([
            {"text": "Перейти в наблюдение",
             "callback_data": CB_AIGATE_SET_SHADOW},
        ])
    inline.append([
        {"text": "📜 Последние 10",
         "callback_data": CB_AIGATE_RECENT},
    ])
    inline.append([{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}])

    return text, {"inline_keyboard": inline}


async def _handle_aigate_recent(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Последние 10 решений AI-Gate. Таблица: время · символ · side · verdict."""
    try:
        recs = memory.get_ai_gate_recent(10)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_ai_gate_recent: {exc}")
        recs = []
    if not recs:
        return _card("AI-Gate · последние 10", "📜", ["Решений пока нет"])
    body: list[str] = []
    for r in recs:
        ts = _parse_iso(r.get("ts"))
        ts_s = ts.strftime("%d.%m %H:%M") if ts else (r.get("ts") or "-")
        symbol = str(r.get("symbol") or "-")
        side = str(r.get("side") or "-")
        verdict_raw = str(r.get("verdict") or "").lower()
        verdict_ru = _ru_verdict(verdict_raw)
        applied_mark = " ✓" if r.get("applied") else ""
        # Точечный индикатор по verdict.
        dot = _status_dot({
            "approve": "ok",
            "veto": "bad",
            "error": "warn",
        }.get(verdict_raw, "off"))
        # Выровненная строка: 11-симв время, 8 — символ, 5 — side, остаток — verdict.
        sym_padded = (symbol[:8]).ljust(8)
        side_padded = (side[:5]).ljust(5)
        body.append(
            f"{dot} {ts_s.ljust(11)} {sym_padded} {side_padded} {verdict_ru}{applied_mark}"
        )
        reason = str(r.get("reason") or "").strip()
        if reason:
            if len(reason) > 60:
                reason = reason[:57] + "..."
            body.append(f"  «{reason}»")
    return _card("AI-Gate · последние 10", "📜", body)


async def _handle_why(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Отклонённые сигналы: группировка за 24ч + последнее отклонение."""
    try:
        counts = memory.get_rejected_counts(24)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_rejected_counts: {exc}")
        counts = []
    try:
        last = memory.get_last_rejected_check()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_last_rejected_check: {exc}")
        last = None

    total = sum(c["count"] for c in counts)
    body: list[str] = [
        _label("За 24ч отклонено", str(total)),
    ]
    if counts:
        body.append(_subhr_line())
        for c in counts:
            cnt = int(c["count"])
            # Цветной индикатор интенсивности: > 5 = bad, 1..5 = warn, 0 = off.
            if cnt > 5:
                dot = _status_dot("bad")
            elif cnt >= 1:
                dot = _status_dot("warn")
            else:
                dot = _status_dot("off")
            body.append(f"{dot} {_label(_ru_filter_tag(c['filter']), str(cnt), 22)}")
    else:
        body.append("  (отклонений нет)")

    body.append(_subhr_line())
    if last:
        ts = _parse_iso(last.get("ts"))
        minutes_ago = "?"
        if ts:
            now = datetime.now(tz=timezone.utc)
            minutes_ago = str(max(0, int((now - ts).total_seconds() // 60)))
        symbol = last.get("symbol") or "-"
        flt = last.get("filter") or "-"
        detail = str(last.get("detail") or "").strip()
        if len(detail) > 200:
            detail = detail[:197] + "..."
        body.append(f"Последнее ({minutes_ago} мин назад):")
        body.append(f"  {symbol} → {_ru_filter_tag(flt)}")
        if detail:
            body.append(f"  «{detail}»")
    else:
        body.append("Последнее: отклонений не было")

    inline = {
        "inline_keyboard": [
            [{"text": "🤖 Спросить AI-аналитика",
              "callback_data": CB_WHY_AI}],
            [{"text": "🛡 Только AI-Gate блокировки",
              "callback_data": CB_WHY_GATE_ONLY}],
            [{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return _card("Почему мимо?", "🔍", body), inline


async def _handle_why_ai(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    try:
        last = memory.get_last_rejected_check()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_last_rejected_check: {exc}")
        last = None
    if not last:
        return _card("AI-разбор", "🤖", ["Отклонений пока нет — разбирать нечего"])
    try:
        errors = memory.get_recent_errors(5)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_recent_errors: {exc}")
        errors = []
    try:
        explanation = await ai_analyst.explain_last_rejection(
            session, last, errors
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] explain_last_rejection: {exc}")
        explanation = "Объяснение временно недоступно."
    symbol = last.get("symbol") or "-"
    flt = last.get("filter") or "-"
    body = [
        _label("Символ", str(symbol)),
        _label("Фильтр", _ru_filter_tag(flt)),
        _subhr_line(),
        str(explanation),
    ]
    return _card("AI-разбор", "🤖", body)


async def _handle_why_gate_only(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Только AI-Gate блокировки за 24ч."""
    try:
        counts = memory.get_rejected_counts(24)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_rejected_counts(gate): {exc}")
        counts = []
    gate_counts = [
        c for c in counts if str(c.get("filter") or "").startswith("ai_gate")
    ]
    total = sum(c["count"] for c in gate_counts)
    body: list[str] = []
    if not gate_counts:
        body.append("За 24 часа AI-Gate не блокировал сделок")
    else:
        body.append(_label("Всего", str(total)))
        body.append(_subhr_line())
        for c in gate_counts:
            cnt = int(c["count"])
            if cnt > 5:
                dot = _status_dot("bad")
            elif cnt >= 1:
                dot = _status_dot("warn")
            else:
                dot = _status_dot("off")
            body.append(f"{dot} {_label(_ru_filter_tag(c['filter']), str(cnt), 22)}")
    return _card("AI-Gate блокировки", "🛡", body)


async def _handle_logs(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    variant: str = "base",
) -> tuple[str, dict[str, Any]]:
    """journalctl через asyncio.create_subprocess_shell с таймаутом 5с.

    variant: "base" (последние 40), "errors" (grep ошибки), "aigate" (grep AI-GATE).
    """
    base_cmd = "journalctl -u zenith -n 40 --no-pager -o cat 2>/dev/null"
    if variant == "errors":
        cmd = (
            "journalctl -u zenith -n 400 --no-pager -o cat 2>/dev/null | "
            "grep -E 'ошибка|ERROR|трейсбек|Exception|Error' | tail -40"
        )
    elif variant == "aigate":
        cmd = (
            "journalctl -u zenith -n 400 --no-pager -o cat 2>/dev/null | "
            "grep 'AI-GATE' | tail -40"
        )
    else:
        cmd = base_cmd

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=5
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            stdout = b""
        text = (stdout or b"").decode("utf-8", errors="replace").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] journalctl ошибка: {exc}")
        text = ""

    if not text:
        text = (
            "(логи пусты)\n\n"
            "Подсказка: если бот запущен, но journal ничего не показывает, "
            "проверьте что PYTHONUNBUFFERED=1 выставлен в zenith.service."
        )

    # Обрезаем с хвоста до 3800 символов.
    if len(text) > 3800:
        text = "...\n" + text[-3800:]

    hint = {
        "errors": "Фильтр: только ошибки",
        "aigate": "Фильтр: только AI-GATE",
        "base": "Последние 40 строк журнала",
    }.get(variant, "Логи")

    body = [hint, _subhr_line(), f"<pre>{text}</pre>"]
    msg = _card("Логи", "📝", body)

    inline = {
        "inline_keyboard": [
            [
                {"text": "🔄 Обновить", "callback_data": CB_LOGS_REFRESH},
            ],
            [
                {"text": "🔍 Только ошибки", "callback_data": CB_LOGS_ERRORS},
                {"text": "🛡 Только AI-Gate", "callback_data": CB_LOGS_AIGATE},
            ],
            [{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return msg, inline


async def _handle_startstop_panic_menu(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Объединённая карточка-перекрёсток для широкой кнопки главного меню.

    Две секции - «Старт/Стоп» (текущий статус торговли + DRY_RUN) и «Panic
    Sell» (закрытие всех позиций reduce-only). Сами действия выполняются в
    подменю CB_STARTSTOP / CB_PANIC, сюда вынесены только переходы.
    """
    g = _g(state)
    bot_running = bool(g.get("bot_running", True))
    bot_dot = _status_dot("ok" if bot_running else "bad")
    status_s = "запущен" if bot_running else "на паузе"
    dry_on = bool(getattr(config, "DRY_RUN", False))
    dry_label = "ВКЛ" if dry_on else "ВЫКЛ"
    dry_dot = _status_dot("warn" if dry_on else "ok")
    body = [
        "Старт / Стоп",
        _label("  Статус", f"{bot_dot} {status_s}"),
        _label("  DRY_RUN", f"{dry_dot} {dry_label}"),
        _subhr_line(),
        "Panic Sell",
        "  Закрытие всех открытых позиций",
        "  reduce-only маркетом и пауза.",
        "  Подтверждение в два шага.",
    ]
    inline = {
        "inline_keyboard": [
            [
                {"text": "⏯ Старт / Стоп", "callback_data": CB_STARTSTOP},
                {"text": "🚨 PANIC SELL", "callback_data": CB_PANIC},
            ],
            [{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return _card("Старт/Стоп · PANIC SELL", "⏯", body), inline


async def _handle_analyst(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Главное меню AI-Аналитика (FEAT-007 / C3).

    Карточка с описанием возможностей + 4 примера вопросов + кнопка ввода
    своего вопроса.
    """
    body = [
        "Я отвечаю на вопросы по статистике вашего бота за 30 дней.",
        "Задайте вопрос своими словами или выберите один из примеров.",
    ]
    text = _card("AI-Аналитик", "🤖", body)
    inline: list[list[dict[str, Any]]] = []
    for cb_data, question in _ANALYST_EXAMPLES:
        inline.append([
            {"text": f"💡 {question}", "callback_data": cb_data},
        ])
    inline.append([
        {"text": "✏ Написать свой вопрос", "callback_data": CB_ANALYST_ASK},
    ])
    inline.append([{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}])
    return text, {"inline_keyboard": inline}


async def _handle_analyst_ask(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> tuple[str, dict[str, Any]]:
    """Перевод FSM в режим ожидания свободного вопроса (5 минут).

    Если активен другой FSM (ключи или блоки) — вежливо отказываем.
    """
    busy = (
        chat_id in _key_fsm_state
        or chat_id in _blocks_fsm_state
    )
    if busy:
        text = _card(
            "AI-Аналитик",
            "🤖",
            ["Сначала завершите текущую операцию."],
        )
        kb = {"inline_keyboard": [
            [{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}],
        ]}
        return text, kb

    _analyst_fsm_state[chat_id] = {
        "mode": "awaiting_question",
        "started": time.time(),
    }
    body = [
        "Пришлите вопрос одним сообщением.",
        "Срок: 5 минут.",
    ]
    text = _card("AI-Аналитик", "🤖", body)
    kb = {"inline_keyboard": [
        [{"text": "❌ Отмена", "callback_data": CB_ANALYST_CANCEL}],
    ]}
    return text, kb


def _build_analyst_context(state: dict[str, Any]) -> str:
    """Сборка контекстного блока для Groq (только memory.* + state, без сети).

    Возвращает многострочный текст ~1500-2000 символов с разделами:
    сводка 30д, эквити/просадка, открытые позиции, AI-Gate 24ч/30д,
    статистика по символам, последние 20 сделок.
    """
    g = _g(state)
    lines: list[str] = []

    # 1) Сводка 30д.
    trades_30 = memory.get_trades_since(30) or []
    closed = [
        t for t in trades_30
        if str(t.get("outcome") or "").upper() in ("WIN", "LOSS")
    ]
    wins = sum(1 for t in closed if str(t["outcome"]).upper() == "WIN")
    losses = sum(1 for t in closed if str(t["outcome"]).upper() == "LOSS")
    total_closed = wins + losses
    winrate = (wins / total_closed * 100.0) if total_closed else 0.0
    pnl_sum = sum(float(t.get("pnl") or 0.0) for t in closed)

    lines.append("== СТАТИСТИКА 30 ДНЕЙ ==")
    lines.append(_label("Сделок", _fmt_num(len(trades_30), 0)))
    lines.append(_label("Закрыто", _fmt_num(total_closed, 0)))
    lines.append(_label("Выигрыши", _fmt_num(wins, 0)))
    lines.append(_label("Проигрыши", _fmt_num(losses, 0)))
    lines.append(_label("Winrate", f"{_fmt_num(winrate, 2)}%"))
    lines.append(_label("PnL сумма", _fmt_num(pnl_sum, 2)))
    lines.append(_subhr_line())

    # 2) Эквити и просадка.
    equity_start = float(g.get("equity_start") or 0.0)
    cumulative_pnl = float(g.get("cumulative_pnl") or 0.0)
    equity_now = equity_start + cumulative_pnl
    try:
        drawdown = float(memory.get_current_drawdown() or 0.0)
    except Exception:  # noqa: BLE001
        drawdown = 0.0

    lines.append("== БАЛАНС ==")
    lines.append(_label("Эквити старт", _fmt_num(equity_start, 2)))
    lines.append(_label("Накопл. PnL", _fmt_num(cumulative_pnl, 2)))
    lines.append(_label("Эквити сейчас", _fmt_num(equity_now, 2)))
    lines.append(_label("Просадка", f"{_fmt_num(drawdown, 2)}%"))
    lines.append(_subhr_line())

    # 3) Открытые позиции.
    open_list: list[str] = []
    for sym, sym_state in (state.get("symbols") or {}).items():
        if not isinstance(sym_state, dict):
            continue
        trade = sym_state.get("open_trade")
        if not trade:
            continue
        side = str(trade.get("side") or "-")
        entry = trade.get("entry_price")
        qty = trade.get("qty")
        open_list.append(
            f"  - {sym} {side} entry={_fmt_num(entry, 4)} "
            f"qty={_fmt_num(qty, 4)}"
        )
    lines.append("== ОТКРЫТЫЕ ПОЗИЦИИ ==")
    if open_list:
        lines.extend(open_list)
    else:
        lines.append("  (нет)")
    lines.append(_subhr_line())

    # 4) AI-Gate 24ч и 30д.
    try:
        gate_24 = memory.get_ai_gate_stats(24) or {}
    except Exception:  # noqa: BLE001
        gate_24 = {}
    try:
        gate_30 = memory.get_ai_gate_stats(720) or {}
    except Exception:  # noqa: BLE001
        gate_30 = {}
    lines.append("== AI-GATE ==")
    lines.append(_label(
        "24ч",
        f"approve={gate_24.get('approve', 0)} "
        f"veto={gate_24.get('veto', 0)} "
        f"error={gate_24.get('error', 0)} "
        f"total={gate_24.get('total', 0)} "
        f"applied={gate_24.get('applied', 0)}",
    ))
    lines.append(_label(
        "30д",
        f"approve={gate_30.get('approve', 0)} "
        f"veto={gate_30.get('veto', 0)} "
        f"error={gate_30.get('error', 0)} "
        f"total={gate_30.get('total', 0)} "
        f"applied={gate_30.get('applied', 0)}",
    ))
    lines.append(_subhr_line())

    # 5) Per-symbol stats (топ по pnl_sum).
    try:
        per_sym = memory.get_per_symbol_stats(30) or []
    except Exception:  # noqa: BLE001
        per_sym = []
    lines.append("== ПО ПАРАМ (30д) ==")
    if per_sym:
        for row in per_sym:
            lines.append(
                "  - "
                + _label(str(row.get("symbol") or "-"), "")
                + f"cnt={row.get('count', 0)} "
                + f"win={row.get('wins', 0)} "
                + f"loss={row.get('losses', 0)} "
                + f"wr={_fmt_num(row.get('winrate', 0.0), 1)}% "
                + f"pnl={_fmt_num(row.get('pnl_sum', 0.0), 2)}"
            )
    else:
        lines.append("  (нет данных)")
    lines.append(_subhr_line())

    # 6) Последние 20 сделок (новые сверху).
    last20 = list(reversed(trades_30))[:20]
    lines.append("== ПОСЛЕДНИЕ 20 СДЕЛОК ==")
    if last20:
        for t in last20:
            sym = str(t.get("symbol") or "-")
            side = str(t.get("side") or "-")
            pnl_v = t.get("pnl")
            outcome = str(t.get("outcome") or "OPEN").upper()
            lines.append(
                f"  - {sym} {side} pnl={_fmt_num(pnl_v, 2)} {outcome}"
            )
    else:
        lines.append("  (нет данных)")

    return "\n".join(lines)


async def _ask_analyst(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    question: str,
) -> str:
    """Задать вопрос Groq и вернуть отформатированную карточку-ответ.

    При пустом ответе или ошибке возвращает понятное сообщение.
    """
    system = (
        "Ты — AI-аналитик торгового бота Zenith-Control. "
        "Отвечаешь на русском, строго по фактам из контекста. "
        "Если данных не хватает — честно говоришь."
    )
    context_block = _build_analyst_context(state)
    prompt = (
        system
        + "\n\nCONTEXT:\n"
        + context_block
        + "\n\nQUESTION: "
        + str(question or "")
    )
    try:
        text = await ai_groq.call_groq_text(
            session,
            prompt,
            max_output_tokens=1024,
            temperature=0.3,
            timeout=25,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] AI-Аналитик: ошибка call_groq_text: {exc}")
        text = ""
    if not text or not str(text).strip():
        return _card(
            "AI-Аналитик · ответ",
            "🤖",
            ["Не удалось получить ответ. Попробуйте позже."],
        )
    body_lines = str(text).splitlines() or [str(text)]
    return _card("AI-Аналитик · ответ", "🤖", body_lines)


async def _handle_startstop_menu(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    g = _g(state)
    bot_running = bool(g.get("bot_running", True))
    bot_dot = _status_dot("ok" if bot_running else "bad")
    status_s = "запущен" if bot_running else "на паузе"
    dry_on = bool(getattr(config, "DRY_RUN", False))
    dry_label = "ВКЛ" if dry_on else "ВЫКЛ"
    dry_dot = _status_dot("warn" if dry_on else "ok")
    body = [
        _label("Статус", f"{bot_dot} {status_s}"),
        _label("DRY_RUN", f"{dry_dot} {dry_label}"),
    ]
    text = _card("Старт / Стоп", "⏯", body)
    dry_btn_text = (
        "Выключить DRY_RUN" if dry_on else "Включить DRY_RUN"
    )
    inline: list[list[dict[str, Any]]] = []
    if bot_running:
        inline.append([
            {"text": "⏸ Пауза (позиции сохраняются)",
             "callback_data": CB_STOP_BOT},
        ])
    else:
        inline.append([
            {"text": "▶ Старт / Возобновить", "callback_data": CB_START_BOT},
        ])
    inline.append([{"text": dry_btn_text, "callback_data": CB_TOGGLE_DRY_RUN}])
    inline.append([{"text": "🚨 PANIC SELL всё", "callback_data": CB_PANIC}])
    inline.append([{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}])
    return text, {"inline_keyboard": inline}


async def _handle_start_bot(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = True
    return "✅ Торговля <b>запущена</b>. Бот снова ищет сигналы."


async def _handle_stop_bot(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = False
    return "⏸ Торговля <b>остановлена</b>. Открытые позиции продолжают управляться."


async def _handle_toggle_dry_run(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Переключение DRY_RUN: в памяти + запись в .env для следующих стартов."""
    new_val = not bool(getattr(config, "DRY_RUN", False))
    setattr(config, "DRY_RUN", new_val)
    ok = _write_env_var("DRY_RUN", "true" if new_val else "false")
    if not ok:
        return (
            f"⚠ DRY_RUN в памяти переключён на "
            f"{'ВКЛ' if new_val else 'ВЫКЛ'}, но запись в .env не удалась."
        )
    return (
        f"✅ DRY_RUN переключён на <b>{'ВКЛ' if new_val else 'ВЫКЛ'}</b>.\n"
        f"Значение применено сразу (без рестарта) и сохранено в .env."
    )


async def _handle_kill_clear(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Снять kill-switch (любой: DAILY / WEEKLY / MDD) вручную."""
    g = _g(state)
    prev = str(g.get("kill_switch_state") or "NONE")
    if prev == "NONE":
        return "Kill-switch не активен, снимать нечего."
    g["kill_switch_state"] = "NONE"
    g["kill_until_utc"] = None
    g["kill_detail"] = ""
    return (
        f"🆘 Kill-switch <b>{prev}</b> снят вручную. Торговля возобновится "
        f"при bot_running=on."
    )


# --- AI-Gate: переключение режима с two-step confirm -----------------------

def _set_gate_mode_safely(new_mode: str) -> tuple[bool, str]:
    """Валидирует значение, записывает в .env атомарно и применяет в памяти."""
    new_mode = (new_mode or "").strip().lower()
    if new_mode not in ("off", "shadow", "active"):
        return False, f"Недопустимое значение: {new_mode!r}"
    if not _write_env_var("AI_TRADE_GATE_MODE", new_mode):
        return False, "Не удалось записать .env"
    setattr(config, "AI_TRADE_GATE_MODE", new_mode)
    return True, new_mode


async def _handle_aigate_set_confirm(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    new_mode: str,
) -> tuple[str, dict[str, Any]]:
    """Первый шаг: показать диалог подтверждения."""
    current = str(
        getattr(config, "AI_TRADE_GATE_MODE", "off") or "off"
    ).lower()
    target_ru = {
        "active": "активен",
        "shadow": "наблюдение",
        "off": "выключен",
    }.get(new_mode, new_mode)
    current_ru = {
        "active": "активен",
        "shadow": "наблюдение",
        "off": "выключен",
    }.get(current, current)
    body = [
        _label("Сейчас", current_ru),
        _label("Станет", target_ru),
        _subhr_line(),
        "Подтвердить?",
    ]
    text = _card("Переключение AI-Gate", "🛡", body)
    inline = {
        "inline_keyboard": [
            [
                {"text": "✅ Да, переключить",
                 "callback_data": f"{CB_AIGATE_CONFIRM_PREFIX}{new_mode}"},
                {"text": "❌ Отмена",
                 "callback_data": CB_AIGATE},
            ],
        ]
    }
    return text, inline


async def _handle_aigate_confirm(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    new_mode: str,
) -> str:
    ok, result = _set_gate_mode_safely(new_mode)
    if not ok:
        return _card(
            "AI-Gate",
            "🛡",
            [f"Не удалось переключить: {result}"],
        )
    return _card(
        "AI-Gate переключён",
        "🛡",
        [
            _label("Режим", str(result)),
            "Применено сразу (без рестарта)",
            "Сохранено в .env",
        ],
    )


# --- PANIC SELL (two-step confirm) -----------------------------------------

async def _handle_panic(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    body = [
        "Будут закрыты все открытые позиции",
        f"по {', '.join(config.SYMBOLS)}",
        "reduce-only маркетом, торговля встанет.",
        _subhr_line(),
        "Вы уверены?",
    ]
    text = _card("PANIC SELL — подтверждение", "🚨", body)
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚠ ДА, ЗАКРЫТЬ ВСЁ", "callback_data": CB_PANIC_CONFIRM},
                {"text": "Отмена", "callback_data": CB_PANIC_CANCEL},
            ],
        ]
    }
    return text, keyboard


async def _handle_panic_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = False
    if getattr(config, "DRY_RUN", False):
        return _card(
            "PANIC SELL",
            "🚨",
            [
                "[DRY RUN] имитация",
                "Реальные ордера не отправлены",
                "Торговля поставлена на паузу",
            ],
        )
    total_orders = 0
    for sym in config.SYMBOLS:
        try:
            results = await EXCHANGE.panic_sell(session, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] Ошибка panic_sell({sym}): {exc}")
            results = []
        total_orders += len(results or [])
    if total_orders == 0:
        return _card(
            "PANIC SELL",
            "🚨",
            ["Открытых позиций не было", "Торговля поставлена на паузу"],
        )
    return _card(
        "PANIC SELL выполнен",
        "🚨",
        [
            _label("Ордеров", str(total_orders)),
            _label("Символов", str(len(config.SYMBOLS))),
            "Торговля поставлена на паузу",
        ],
    )


async def _handle_panic_cancel(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return "Отменено. Позиции не тронуты, торговля продолжается."


# --- Переключение Демо/Реал (two-step) -------------------------------------

async def _handle_mode_switch(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Первый шаг: показать текущий/будущий режим + warning."""
    is_testnet_now = bool(config.IS_TESTNET)
    current_dot = _status_dot("ok" if is_testnet_now else "bad")
    target_dot = _status_dot("bad" if is_testnet_now else "ok")
    current_ru = (
        "ДЕМО (OKX testnet, виртуальные 5000 USDT)"
        if is_testnet_now
        else "РЕАЛ (OKX mainnet, реальные деньги)"
    )
    target_ru = (
        "РЕАЛ (OKX mainnet, реальные деньги)"
        if is_testnet_now
        else "ДЕМО (OKX testnet, виртуальные 5000 USDT)"
    )

    # Открытые позиции предупреждение.
    open_count = sum(
        1 for s in state.get("symbols", {}).values() if s.get("open_trade")
    )
    body: list[str] = [
        _label("Сейчас", f"{current_dot} {current_ru}"),
        _label("Станет", f"{target_dot} {target_ru}"),
    ]

    real_warn_lines: list[str] = []
    if is_testnet_now:
        real_warn_lines = [
            "ВНИМАНИЕ — реальные деньги.",
            "Все сделки уйдут на боевой OKX-аккаунт.",
            "Убедитесь:",
            "  · OKX_API_KEY_REAL и др. заполнены",
            "    (🔑 КЛЮЧИ API → OKX Real *)",
            "  · открытых позиций на демо нет",
        ]

    open_warn_lines: list[str] = []
    if open_count > 0:
        account_label = "демо" if is_testnet_now else "реал"
        open_warn_lines = [
            f"Сейчас открыто позиций: {open_count} ({account_label})",
            "После переключения они останутся",
            f"на {account_label}-аккаунте, но бот не будет",
            "ими управлять (ключи поменяются).",
            "Сначала закройте через 🚨 PANIC SELL.",
        ]

    keys_warn_lines: list[str] = []
    keys_blocked = False
    if is_testnet_now:
        if not config.OKX_API_KEY_REAL:
            keys_blocked = True
            keys_warn_lines = [
                "❌ Реал-ключи не заполнены",
                "В .env пусто OKX_API_KEY_REAL.",
                "Заполните: 🔑 КЛЮЧИ API → OKX Real *",
            ]
    else:
        if not config.OKX_API_KEY_DEMO:
            keys_blocked = True
            keys_warn_lines = [
                "❌ Демо-ключи не заполнены",
                "В .env пусто OKX_API_KEY (демо).",
                "Заполните: 🔑 КЛЮЧИ API → OKX Demo *",
            ]

    if real_warn_lines:
        body.append(_subhr_line())
        body.extend(real_warn_lines)
    if open_warn_lines:
        body.append(_subhr_line())
        body.extend(open_warn_lines)
    if keys_warn_lines:
        body.append(_subhr_line())
        body.extend(keys_warn_lines)

    text = _card("Демо/Реал", "🏦", body)

    inline_rows: list[list[dict[str, Any]]] = []
    if keys_blocked:
        inline_rows.append([
            {"text": "❌ Отмена", "callback_data": CB_MODE_SWITCH_NO},
        ])
    else:
        confirm_text = (
            "⚠ Да, переключить на РЕАЛ" if is_testnet_now
            else "✅ Да, переключить на ДЕМО"
        )
        inline_rows.append([
            {"text": confirm_text, "callback_data": CB_MODE_SWITCH_OK},
            {"text": "❌ Отмена", "callback_data": CB_MODE_SWITCH_NO},
        ])
    return text, {"inline_keyboard": inline_rows}


async def _handle_mode_switch_ok(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Подтверждение переключения: запись в .env + SIGTERM."""
    is_testnet_now = bool(config.IS_TESTNET)
    new_val = "false" if is_testnet_now else "true"
    target_label = (
        "РЕАЛ (OKX mainnet)" if is_testnet_now else "ДЕМО (OKX testnet)"
    )
    if not _write_env_var("IS_TESTNET", new_val):
        return _card(
            "Демо/Реал",
            "🏦",
            ["Не удалось записать IS_TESTNET в .env", "Переключение отменено"],
        )
    asyncio.get_event_loop().call_later(1.0, _self_terminate)
    return _card(
        "Демо/Реал — сохранено",
        "🏦",
        [
            _label("Режим", target_label),
            "Бот перезапускается (~20 секунд)",
        ],
    )


def _self_terminate() -> None:
    """Послать себе SIGTERM - systemd с Restart=always перезапустит."""
    try:
        print("[TG] Самоперезапуск через SIGTERM (Demo/Real или ключи API)")
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка SIGTERM: {exc}")


async def _handle_mode_switch_no(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return "Переключение режима отменено."


# --- Ключи API (FSM) -------------------------------------------------------

# Порядок важен - по нему строим меню.
_KEY_UI_NAMES: list[tuple[str, str, str]] = [
    # (UI-name, env-variable, emoji)
    ("OKX Demo Key", "OKX_API_KEY", "🟦"),
    ("OKX Demo Secret", "OKX_API_SECRET", "🟦"),
    ("OKX Demo Passphrase", "OKX_PASSPHRASE", "🟦"),
    ("OKX Real Key", "OKX_API_KEY_REAL", "🟥"),
    ("OKX Real Secret", "OKX_API_SECRET_REAL", "🟥"),
    ("OKX Real Passphrase", "OKX_PASSPHRASE_REAL", "🟥"),
    ("Groq API Key", "GROQ_API_KEY", "🤖"),
    ("NewsAPI Key", "NEWS_API_KEY", "📰"),
    ("Telegram Token", "TELEGRAM_TOKEN", "💬"),
]

_ENV_TO_UINAME = {env: name for name, env, _ in _KEY_UI_NAMES}


def _validate_key_value(env_name: str, value: str) -> tuple[bool, str]:
    """Минимальная проверка длины. True если прошло."""
    v = value or ""
    n = len(v)
    if env_name in ("OKX_API_KEY", "OKX_API_SECRET",
                    "OKX_API_KEY_REAL", "OKX_API_SECRET_REAL"):
        if n < 32:
            return False, f"длина {n}, ожидается >= 32"
    elif env_name in ("OKX_PASSPHRASE", "OKX_PASSPHRASE_REAL"):
        if n < 6:
            return False, f"длина {n}, ожидается >= 6"
    elif env_name == "GROQ_API_KEY":
        if n < 20:
            return False, f"длина {n}, ожидается >= 20"
    elif env_name == "NEWS_API_KEY":
        if n < 20:
            return False, f"длина {n}, ожидается >= 20"
    elif env_name == "TELEGRAM_TOKEN":
        if n < 40 or ":" not in v:
            return False, f"длина {n}, ожидается >= 40 и содержит ':'"
    return True, ""


async def _handle_keys_menu(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Меню замены ключей."""
    body = [
        "Внимание:",
        "  · сообщение с ключом будет удалено",
        "  · после замены бот перезапустится",
        "    (~20 секунд)",
        _subhr_line(),
        "OKX Демо (если IS_TESTNET=true)",
        "OKX Реал (если IS_TESTNET=false)",
        "Общие для всех режимов",
    ]
    text = _card("Ключи API", "🔑", body)
    rows: list[list[dict[str, Any]]] = []
    for ui_name, env_name, emoji in _KEY_UI_NAMES:
        rows.append([{
            "text": f"{emoji} {ui_name}",
            "callback_data": f"{CB_KEY_PREFIX}{env_name}",
        }])
    rows.append([{"text": "📤 Экспорт .env", "callback_data": CB_EXPORT_ENV}])
    rows.append([{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}])
    return text, {"inline_keyboard": rows}


async def _handle_key_start(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    env_name: str,
    chat_id: int,
) -> tuple[str, dict[str, Any]]:
    """Начать FSM-поток замены ключа env_name. Показать предупреждения если
    нужно, затем перевести FSM в состояние ожидания значения."""
    ui_name = _ENV_TO_UINAME.get(env_name, env_name)

    # Проверка на открытые позиции для OKX-ключей.
    warnings: list[str] = []
    is_okx_demo = env_name in (
        "OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"
    )
    is_okx_real = env_name in (
        "OKX_API_KEY_REAL", "OKX_API_SECRET_REAL", "OKX_PASSPHRASE_REAL"
    )
    open_count = sum(
        1 for s in state.get("symbols", {}).values() if s.get("open_trade")
    )
    if is_okx_demo and config.IS_TESTNET and open_count > 0:
        warnings.append(
            f"Открыто {open_count} демо-позиций. После замены"
        )
        warnings.append("демо-ключа бот потеряет с ними связь.")
        warnings.append("Сначала закройте через 🚨 PANIC SELL.")
    if is_okx_real and (not config.IS_TESTNET) and open_count > 0:
        warnings.append(
            f"Открыто {open_count} РЕАЛ-позиций. После замены"
        )
        warnings.append("реал-ключа бот потеряет с ними связь —")
        warnings.append("они останутся на бирже без управления.")
        warnings.append("Сначала закройте через 🚨 PANIC SELL.")
    if env_name == "TELEGRAM_TOKEN":
        warnings.append("КРИТИЧНО: смена TELEGRAM_TOKEN")
        warnings.append("разорвёт связь этого чата с ботом.")
        warnings.append("Восстановление только через SSH.")

    # Переводим FSM в состояние «ждём значение».
    _key_fsm_state[chat_id] = {
        "env_name": env_name,
        "pending_value": None,
        "started": time.time(),
    }

    body: list[str] = [_label("Ключ", str(ui_name))]
    if warnings:
        body.append(_subhr_line())
        body.extend(warnings)
    body.append(_subhr_line())
    body.append("Пришлите новое значение одним сообщением.")
    body.append("Сообщение будет удалено сразу.")
    body.append("Время на ввод: 5 минут.")

    text = _card("Замена ключа", "🔑", body)
    inline = {
        "inline_keyboard": [
            [{"text": "❌ Отмена", "callback_data": CB_KEY_CANCEL}],
        ]
    }
    return text, inline


async def _handle_key_cancel(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    chat_id: int,
) -> str:
    """Отмена замены ключа: чистим FSM."""
    _key_fsm_state.pop(chat_id, None)
    return "❌ Замена ключа отменена."


async def _handle_key_confirm(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    env_name: str,
    chat_id: int,
) -> str:
    """Подтверждение записи: _write_env_var + SIGTERM."""
    fsm = _key_fsm_state.get(chat_id)
    if not fsm or fsm.get("env_name") != env_name:
        return "⚠ Сессия замены ключа истекла или не найдена."
    value = fsm.get("pending_value")
    if not value:
        return "⚠ Значение не получено. Начните заново."
    # Таймаут.
    if time.time() - float(fsm.get("started") or 0) > _KEY_FSM_TIMEOUT_SEC:
        _key_fsm_state.pop(chat_id, None)
        return "⚠ Сессия замены ключа истекла (5 минут). Начните заново."
    if not _write_env_var(env_name, value):
        _key_fsm_state.pop(chat_id, None)
        return "⚠ Не удалось записать .env. Замена отменена."
    _key_fsm_state.pop(chat_id, None)
    asyncio.get_event_loop().call_later(1.0, _self_terminate)
    ui_name = _ENV_TO_UINAME.get(env_name, env_name)
    return (
        f"✅ Ключ <b>{ui_name}</b> успешно обновлён.\n"
        f"Бот перезапускается... (~20 секунд)"
    )


# --- Квота Groq API (пассивный мониторинг) --------------------------------

async def _handle_groq_quota(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Показать текущее состояние квоты Groq API.

    Использует пассивный снапшот ai_groq.get_quota_snapshot() - не делает
    дополнительных сетевых вызовов. Снапшот обновляется на каждом HTTP-ответе
    от Groq (macro-sentinel / ai_regime / ai_trade_gate).
    """
    import ai_groq
    snap = ai_groq.get_quota_snapshot()

    inline = {
        "inline_keyboard": [
            [{"text": "🔄 Обновить", "callback_data": CB_GROQ_REFRESH}],
            [{"text": "◀ Назад", "callback_data": CB_BACK_MAIN}],
        ]
    }

    if snap.get("updated_epoch", 0.0) == 0.0:
        body = [
            "Снапшот квоты ещё не получен.",
            _subhr_line(),
            "Дождитесь первого вызова Groq",
            "(macro-sentinel / ai_regime / AI-Gate).",
            "Обычно — в течение минуты после старта.",
        ]
        return _card("Квота Groq", "🤖", body), inline

    age_sec = int(max(0, time.time() - snap["updated_epoch"]))
    if age_sec < 60:
        age_str = f"{age_sec}с назад"
    elif age_sec < 3600:
        age_str = f"{age_sec // 60}м назад"
    else:
        age_str = f"{age_sec // 3600}ч {(age_sec % 3600) // 60}м назад"

    rpd_used = max(0, snap["rpd_limit"] - snap["rpd_remaining"])
    tpd_used = max(0, snap["tpd_limit"] - snap["tpd_remaining"])
    rpm_used = max(0, snap["rpm_limit"] - snap["rpm_remaining"])

    def _pct_label(used: int, lim: int) -> str:
        if lim <= 0:
            return f"{_fmt_num(0.0, 1)}%"
        return f"{_fmt_num((used / lim) * 100.0, 1)}%"

    body = [
        "Сегодня:",
        f"  Запросы {_progress_bar_10(rpd_used, snap['rpd_limit'])}  "
        f"{_fmt_num(rpd_used, 0)} / {_fmt_num(snap['rpd_limit'], 0)}  "
        f"({_pct_label(rpd_used, snap['rpd_limit'])})",
        f"  Токены  {_progress_bar_10(tpd_used, snap['tpd_limit'])}  "
        f"{_fmt_num(tpd_used, 0)} / {_fmt_num(snap['tpd_limit'], 0)}  "
        f"({_pct_label(tpd_used, snap['tpd_limit'])})",
        _subhr_line(),
        "Текущая минута:",
        f"  Запросы {_progress_bar_10(rpm_used, snap['rpm_limit'])}  "
        f"{_fmt_num(rpm_used, 0)} / {_fmt_num(snap['rpm_limit'], 0)}  "
        f"({_pct_label(rpm_used, snap['rpm_limit'])})",
    ]
    reset_lines: list[str] = []
    if snap.get("rpd_reset"):
        reset_lines.append(_label("  Запросы (сутки)", str(snap["rpd_reset"])))
    if snap.get("tpd_reset"):
        reset_lines.append(_label("  Токены (сутки)", str(snap["tpd_reset"])))
    if snap.get("rpm_reset"):
        reset_lines.append(_label("  Минутный лимит", str(snap["rpm_reset"])))
    if reset_lines:
        body.append(_subhr_line())
        body.append("Сброс через:")
        body.extend(reset_lines)
    body.append(_subhr_line())
    body.append(_label("Снапшот", age_str))
    body.append(_subhr_line())
    body.append("Ориентир. потребление:")
    body.append("  · macro-sentinel: ~1/час")
    body.append("  · ai_regime:      ~14/час")
    body.append("  · ai_trade_gate:  0-5/час")
    body.append("  Итого ≈ 360-480 в сутки")

    return _card("Квота Groq", "🤖", body), inline


# --- Диспетчер callback-ов -------------------------------------------------

async def _process_callback(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    cb: dict[str, Any],
) -> None:
    cb_id = cb.get("id")
    data = str(cb.get("data") or "")
    chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id") or 0
    # Жёстко сводим к авторизованному chat_id, т.к. только он проходит проверку.
    try:
        chat_id_int = int(chat_id)
    except (TypeError, ValueError):
        chat_id_int = config.TELEGRAM_CHAT_ID

    result: Any = None

    try:
        # Главное меню / кнопки.
        if data == CB_STATUS:
            result = await _handle_status(session, state)
        elif data == CB_POSITIONS:
            result = await _handle_positions(session, state)
        elif data == CB_AIGATE or data == CB_AIGATE_MENU:
            result = await _handle_aigate(session, state)
        elif data == CB_AIGATE_RECENT:
            result = await _handle_aigate_recent(session, state)
        elif data == CB_AIGATE_SET_OFF:
            result = await _handle_aigate_set_confirm(session, state, "off")
        elif data == CB_AIGATE_SET_SHADOW:
            result = await _handle_aigate_set_confirm(session, state, "shadow")
        elif data == CB_AIGATE_SET_ACTIVE:
            result = await _handle_aigate_set_confirm(session, state, "active")
        elif data.startswith(CB_AIGATE_CONFIRM_PREFIX):
            new_mode = data[len(CB_AIGATE_CONFIRM_PREFIX):]
            result = await _handle_aigate_confirm(session, state, new_mode)
        elif data == CB_REGIMES:
            result = await _handle_regimes(session, state)
        elif data == CB_WHY:
            result = await _handle_why(session, state)
        elif data == CB_WHY_AI:
            result = await _handle_why_ai(session, state)
        elif data == CB_WHY_GATE_ONLY:
            result = await _handle_why_gate_only(session, state)
        elif data == CB_LOGS or data == CB_LOGS_REFRESH:
            result = await _handle_logs(session, state, "base")
        elif data == CB_LOGS_ERRORS:
            result = await _handle_logs(session, state, "errors")
        elif data == CB_LOGS_AIGATE:
            result = await _handle_logs(session, state, "aigate")
        elif data == CB_STARTSTOP:
            result = await _handle_startstop_menu(session, state)
        elif data == CB_STARTSTOP_PANIC:
            result = await _handle_startstop_panic_menu(session, state)
        elif data == CB_ANALYST:
            result = await _handle_analyst(session, state)
        elif data == CB_ANALYST_ASK:
            result = await _handle_analyst_ask(session, state, chat_id_int)
        elif data == CB_ANALYST_EX1:
            result = await _ask_analyst(
                session, state, _ANALYST_EXAMPLES[0][1]
            )
        elif data == CB_ANALYST_EX2:
            result = await _ask_analyst(
                session, state, _ANALYST_EXAMPLES[1][1]
            )
        elif data == CB_ANALYST_EX3:
            result = await _ask_analyst(
                session, state, _ANALYST_EXAMPLES[2][1]
            )
        elif data == CB_ANALYST_EX4:
            result = await _ask_analyst(
                session, state, _ANALYST_EXAMPLES[3][1]
            )
        elif data == CB_ANALYST_CANCEL:
            _analyst_fsm_state.pop(chat_id_int, None)
            result = (
                "👋 Главное меню. Выберите действие кнопкой ниже.",
                set_keyboard(),
            )
        elif data == CB_START_BOT:
            result = await _handle_start_bot(session, state)
        elif data == CB_STOP_BOT:
            result = await _handle_stop_bot(session, state)
        elif data == CB_TOGGLE_DRY_RUN:
            result = await _handle_toggle_dry_run(session, state)
        elif data == CB_PANIC:
            result = await _handle_panic(session, state)
        elif data == CB_PANIC_CONFIRM:
            result = await _handle_panic_confirm(session, state)
        elif data == CB_PANIC_CANCEL:
            result = await _handle_panic_cancel(session, state)
        elif data == CB_MODE_SWITCH:
            result = await _handle_mode_switch(session, state)
        elif data == CB_MODE_SWITCH_OK:
            result = await _handle_mode_switch_ok(session, state)
        elif data == CB_MODE_SWITCH_NO:
            result = await _handle_mode_switch_no(session, state)
        elif data == CB_KILL_CLEAR:
            result = await _handle_kill_clear(session, state)
        elif data == CB_BACK_MAIN:
            result = (
                "👋 Главное меню. Выберите действие кнопкой ниже.",
                set_keyboard(),
            )
        elif data == CB_KEYS:
            result = await _handle_keys_menu(session, state)
        elif data == CB_GROQ or data == CB_GROQ_REFRESH:
            result = await _handle_groq_quota(session, state)
        elif data == CB_AGGR_MENU:
            result = await _handle_aggressiveness_menu(session, state)
        elif data.startswith(CB_AGGR_CONFIRM_PREFIX):
            preset_key = data[len(CB_AGGR_CONFIRM_PREFIX):]
            result = await _handle_aggressiveness_apply(
                session, state, preset_key
            )
        elif data.startswith(CB_AGGR_SET_PREFIX):
            preset_key = data[len(CB_AGGR_SET_PREFIX):]
            result = await _handle_aggressiveness_confirm(
                session, state, preset_key
            )
        elif data == CB_BLOCKS:
            result = await _handle_blocks_menu(session, state)
        elif data == CB_BLOCKS_ADD:
            result = await _handle_blocks_add_start(
                session, state, chat_id_int
            )
        elif data == CB_BLOCKS_CANCEL:
            result = await _handle_blocks_cancel(
                session, state, chat_id_int
            )
        elif data.startswith(CB_BLOCKS_REMOVE_PREFIX):
            target = data[len(CB_BLOCKS_REMOVE_PREFIX):]
            result = await _handle_blocks_remove(session, state, target)
        elif data.startswith(CB_BLOCKS_DURATION_PREFIX):
            duration_value = data[len(CB_BLOCKS_DURATION_PREFIX):]
            result = await _handle_blocks_duration_pick(
                session, state, chat_id_int, duration_value
            )
        elif data == CB_BLOCKS_AUTOSETTINGS:
            result = await _handle_blocks_autosettings(session, state)
        elif data.startswith(CB_BLOCKS_AUTOSET_PREFIX):
            payload = data[len(CB_BLOCKS_AUTOSET_PREFIX):]
            result = await _handle_blocks_autoset(session, state, payload)
        elif data == CB_EXPORT_ENV:
            result = await _handle_env_export(session, state, chat_id_int)
        elif data == CB_PAIRS:
            result = await _handle_per_symbol_stats(session, state)
        elif data == CB_PAIR_PICKER:
            result = await _handle_pair_picker(session, state)
        elif data.startswith(CB_PAIR_BLOCK_PREFIX):
            sym = data[len(CB_PAIR_BLOCK_PREFIX):]
            result = await _handle_pair_block_start(
                session, state, chat_id_int, sym
            )
        elif data.startswith(CB_PAIR_DETAIL_PREFIX):
            sym = data[len(CB_PAIR_DETAIL_PREFIX):]
            result = await _handle_pair_detail(session, state, sym)
        elif data == CB_BT_MENU:
            result = await _handle_backtest_menu(session, state, chat_id_int)
        elif data.startswith(CB_BT_PERIOD_PREFIX):
            period_str = data[len(CB_BT_PERIOD_PREFIX):]
            result = await _handle_backtest_period(
                session, state, chat_id_int, period_str
            )
        elif data == CB_BT_RUN:
            result = await _handle_backtest_run(session, state, chat_id_int)
        elif data == CB_BT_CSV:
            result = await _handle_backtest_csv(session, state, chat_id_int)
        elif data == CB_BT_BACK:
            result = (
                "👋 Главное меню. Выберите действие кнопкой ниже.",
                set_keyboard(),
            )
        elif data.startswith(CB_KEY_PREFIX) and not data.startswith(
            CB_KEY_CONFIRM_PREFIX
        ):
            env_name = data[len(CB_KEY_PREFIX):]
            if env_name in _ENV_TO_UINAME:
                result = await _handle_key_start(
                    session, state, env_name, chat_id_int
                )
            else:
                result = "⚠ Неизвестный ключ."
        elif data.startswith(CB_KEY_CONFIRM_PREFIX):
            env_name = data[len(CB_KEY_CONFIRM_PREFIX):]
            result = await _handle_key_confirm(
                session, state, env_name, chat_id_int
            )
        elif data == CB_KEY_CANCEL:
            result = await _handle_key_cancel(session, state, chat_id_int)
        else:
            result = "Неизвестная команда."
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка обработчика {data}: {exc}")
        result = f"Ошибка обработчика: {exc}"

    if isinstance(result, tuple) and len(result) == 2:
        text, keyboard = result
    else:
        text = result
        keyboard = set_keyboard()

    if cb_id:
        await answer_callback(session, cb_id, "Готово")
    if text:
        await send_message(session, text, reply_markup=keyboard)


async def _process_message(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    msg: dict[str, Any],
) -> None:
    text = (msg.get("text") or "").strip()
    lowered = text.lower()
    chat_id = (msg.get("chat") or {}).get("id") or config.TELEGRAM_CHAT_ID
    try:
        chat_id_int = int(chat_id)
    except (TypeError, ValueError):
        chat_id_int = config.TELEGRAM_CHAT_ID
    message_id = msg.get("message_id")

    # FSM (FEAT-004 / B2): если мы в шаге await_symbol для добавления
    # блока — перехватываем сообщение как тикер.
    blocks_fsm = _blocks_fsm_state.get(chat_id_int)
    if blocks_fsm and blocks_fsm.get("step") == "await_symbol":
        if _blocks_fsm_expired(blocks_fsm):
            _blocks_fsm_clear(chat_id_int)
            await send_message(
                session,
                _card(
                    "Запреты",
                    "🚫",
                    ["Сессия добавления блока истекла (5 минут).",
                     "Начните заново."],
                ),
                reply_markup=set_keyboard(),
            )
            return
        candidate = (text or "").strip().upper()
        if not _looks_like_symbol(candidate):
            await send_message(
                session,
                _card(
                    "Добавить запрет",
                    "🚫",
                    [
                        f"Не похоже на тикер: «{text[:32]}»",
                        _subhr_line(),
                        "Формат: латиница + USDT в конце.",
                        "Например: XRPUSDT, BTCUSDT, SOLUSDT.",
                        _subhr_line(),
                        "Повторите ввод или нажмите «Отмена».",
                    ],
                ),
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "❌ Отмена",
                         "callback_data": CB_BLOCKS_CANCEL},
                    ]]
                },
            )
            return
        # Тикер принят — переходим к шагу выбора длительности.
        blocks_fsm["symbol"] = candidate
        blocks_fsm["step"] = "await_duration"
        blocks_fsm["started"] = time.time()
        body = [
            _label("Пара", candidate),
            _subhr_line(),
            "Выберите длительность блока:",
        ]
        duration_buttons: list[list[dict[str, Any]]] = []
        row: list[dict[str, Any]] = []
        for value, label in _BLOCKS_DURATIONS:
            row.append({
                "text": label,
                "callback_data": f"{CB_BLOCKS_DURATION_PREFIX}{value}",
            })
            if len(row) == 3:
                duration_buttons.append(row)
                row = []
        if row:
            duration_buttons.append(row)
        duration_buttons.append([{
            "text": "❌ Отмена", "callback_data": CB_BLOCKS_CANCEL,
        }])
        await send_message(
            session,
            _card("Добавить запрет", "🚫", body),
            reply_markup={"inline_keyboard": duration_buttons},
        )
        return

    # FSM: если мы ждём значение ключа - перехватываем.
    fsm = _key_fsm_state.get(chat_id_int)
    if fsm and fsm.get("pending_value") is None:
        # Таймаут.
        if time.time() - float(fsm.get("started") or 0) > _KEY_FSM_TIMEOUT_SEC:
            _key_fsm_state.pop(chat_id_int, None)
            await send_message(
                session,
                "⚠ Сессия замены ключа истекла (5 минут). Начните заново.",
                reply_markup=set_keyboard(),
            )
            return
        env_name = str(fsm.get("env_name") or "")
        value = text
        # Удаляем сообщение пользователя с ключом сразу.
        if message_id is not None:
            await delete_message(session, chat_id_int, int(message_id))
        # Валидация длины (без логирования значения).
        ok, reason = _validate_key_value(env_name, value)
        if not ok:
            await send_message(
                session,
                f"⚠ Ключ выглядит неправильно ({reason}).\n"
                f"Повторите ввод или нажмите «Отмена».",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "❌ Отмена", "callback_data": CB_KEY_CANCEL},
                    ]]
                },
            )
            return
        # Сохраняем значение в FSM и показываем confirm.
        fsm["pending_value"] = value
        ui_name = _ENV_TO_UINAME.get(env_name, env_name)
        confirm_kb = {
            "inline_keyboard": [
                [
                    {"text": "✅ Да, заменить",
                     "callback_data": f"{CB_KEY_CONFIRM_PREFIX}{env_name}"},
                    {"text": "❌ Отмена", "callback_data": CB_KEY_CANCEL},
                ],
            ]
        }
        await send_message(
            session,
            (
                f"🔑 <b>Подтверждение замены: {ui_name}</b>\n\n"
                f"Получено значение длиной {len(value)} символов. "
                f"Ваше сообщение удалено.\n\n"
                f"После подтверждения бот перезапустится (~20 секунд)."
            ),
            reply_markup=confirm_kb,
        )
        return

    # FSM (FEAT-007 / C3): если ждём свободный вопрос аналитику —
    # перехватываем сообщение и шлём его в Groq.
    analyst_fsm = _analyst_fsm_state.get(chat_id_int)
    if analyst_fsm and analyst_fsm.get("mode") == "awaiting_question":
        started = float(analyst_fsm.get("started") or 0.0)
        if time.time() - started > _ANALYST_FSM_TIMEOUT_SEC:
            _analyst_fsm_state.pop(chat_id_int, None)
            await send_message(
                session,
                "Сессия аналитика истекла (5 минут). "
                "Откройте 🤖 АНАЛИТИК заново.",
                reply_markup=set_keyboard(),
            )
            return
        question = (text or "").strip()
        if not question:
            await send_message(
                session,
                "Пустой вопрос. Пришлите текст одним сообщением "
                "или нажмите «❌ Отмена».",
                reply_markup={"inline_keyboard": [[
                    {"text": "❌ Отмена",
                     "callback_data": CB_ANALYST_CANCEL},
                ]]},
            )
            return
        _analyst_fsm_state.pop(chat_id_int, None)
        answer = await _ask_analyst(session, state, question)
        await send_message(session, answer, reply_markup=set_keyboard())
        return

    if lowered in ("/start", "/menu", "/help"):
        await send_message(
            session,
            "👋 <b>Zenith-Control Ultimate v3</b>\nВыберите действие кнопкой ниже.",
            reply_markup=set_keyboard(),
        )
        return
    if lowered == "/status":
        text_status, kb = await _handle_status(session, state)
        await send_message(session, text_status, reply_markup=kb)
        return
    # Любое другое сообщение - просто показываем меню.
    await send_message(
        session,
        "Используйте кнопки ниже для управления ботом.",
        reply_markup=set_keyboard(),
    )


async def run_bot(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Основной long-polling цикл. Живёт всё время работы приложения."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[TG] Бот не запущен: нет TELEGRAM_TOKEN или TELEGRAM_CHAT_ID")
        while True:
            await asyncio.sleep(3600)

    print("[TG] Long-polling Telegram запущен")
    offset: Optional[int] = None
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": json.dumps(
                ["message", "callback_query"])}
            if offset is not None:
                params["offset"] = offset
            async with session.get(
                _bot_url("getUpdates"), params=params, timeout=40
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[TG] getUpdates статус {resp.status}: {body[:200]}")
                    await asyncio.sleep(5)
                    continue
                data = await resp.json()
        except aiohttp.ClientError as exc:
            print(f"[TG] Сетевая ошибка getUpdates: {exc}")
            await asyncio.sleep(5)
            continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] Неожиданная ошибка getUpdates: {exc}")
            await asyncio.sleep(5)
            continue

        if not data.get("ok"):
            print(f"[TG] Telegram вернул not ok: {data}")
            await asyncio.sleep(5)
            continue

        updates = data.get("result") or []
        for upd in updates:
            try:
                offset = int(upd.get("update_id", 0)) + 1
            except (TypeError, ValueError):
                pass

            if not _is_authorized(upd):
                cb = upd.get("callback_query")
                if cb and cb.get("id"):
                    try:
                        await answer_callback(
                            session,
                            cb["id"],
                            "Доступ запрещён",
                            show_alert=True,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                continue

            try:
                if upd.get("callback_query"):
                    await _process_callback(session, state, upd["callback_query"])
                elif upd.get("message"):
                    await _process_message(session, state, upd["message"])
            except Exception as exc:  # noqa: BLE001
                print(f"[TG] Ошибка обработки апдейта: {exc}")
