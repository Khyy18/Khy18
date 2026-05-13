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
import signal
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

import ai_analyst
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

# Аналитик (FEAT-007 / C3) — пока заглушка, открывается из главного меню.
CB_ANALYST = "zc:analyst"
# Объединённое подменю «Старт/Стоп · PANIC SELL» — широкая нижняя кнопка
# главного меню. Старые подменю CB_STARTSTOP и CB_PANIC доступны переходом
# внутрь.
CB_STARTSTOP_PANIC = "zc:ssp"

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
    dir_arrow = "↗️" if is_long else "↘️"
    raw_reason = error_reason or ""
    reason_txt = (raw_reason[:200] + "…") if len(raw_reason) > 200 else raw_reason
    utc_now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    text = (
        f"⚠️ <b>СДЕЛКА ЗАБЛОКИРОВАНА (Groq недоступен)</b>\n\n"
        f"Пара: {symbol}\n"
        f"Сторона: {side_label} (планировалась)\n"
        f"Сигнал: {strategy_name}\n"
        f"Цена: {price}\n\n"
        f"🧠 AI-GATE: ❌ ошибка\n"
        f"Причина: {reason_txt}\n\n"
        f"Это не потеря — сделка не открыта из соображений безопасности.\n"
        f"Переключить в наблюдение: кнопка 🛡 AI-GATE → «Наблюдение»\n\n"
        f"⏱ {utc_now}"
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

    # Режимы: две строки для 7 символов (4 + 3).
    regime_blocks: list[str] = []
    for symbol in config.SYMBOLS:
        sym_state = (state.get("symbols") or {}).get(symbol) or {}
        regime = sym_state.get("regime") or {}
        emoji = _regime_emoji(regime.get("regime") or "")
        short_sym = symbol.replace("USDT", "")
        regime_blocks.append(f"{emoji} {short_sym}")
    # Делим на строки по 4 в первой строке и остаток во второй.
    row1 = " ".join(regime_blocks[:4])
    row2 = " ".join(regime_blocks[4:])

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
        "active": "активен (строгая защита)",
        "shadow": "наблюдение (без блокировки)",
        "off": "выключен",
    }.get(gate_mode_raw, gate_mode_raw)

    dry_run_label = "ВКЛ" if getattr(config, "DRY_RUN", False) else "ВЫКЛ"
    mode_label = (
        "ДЕМО (OKX testnet)"
        if config.IS_TESTNET
        else "⚠ РЕАЛ (OKX mainnet, реальные деньги)"
    )

    kill_state = str(g.get("kill_switch_state") or "NONE")
    kill_until_iso = g.get("kill_until_utc")
    if kill_state != "NONE" and kill_until_iso:
        kill_line = f"{kill_state} (до {kill_until_iso})"
    elif kill_state != "NONE":
        kill_line = f"{kill_state} (без срока)"
    else:
        kill_line = "NONE"

    started_epoch = float(g.get("started_epoch") or 0.0)
    uptime = _format_uptime(time.time() - started_epoch) if started_epoch else "-"

    bot_running = "🟢 запущен" if g.get("bot_running", True) else "🔴 на паузе"

    lines = [
        "📊 <b>Статус</b>",
        "",
        f"💰 Баланс: {equity_now:.2f} USDT ({pct_from_start:+.2f}% от старта)",
        f"📈 Сделки: {stats['count']} всего, винрейт {stats['winrate']:.1f}%",
        f"📂 Открыто: {open_cnt} / {total_cnt}",
        "",
        "🎯 Режимы:",
        f"   {row1}",
    ]
    if row2:
        lines.append(f"   {row2}")
    lines += [
        "",
        f"🛡 AI-Gate: {gate_mode_ru}",
        f"   За 24ч: ✅ {gate_stats['approve']}  🚫 {gate_stats['veto']}  "
        f"⚠ {gate_stats['error']}  (всего {gate_stats['total']})",
        "",
        f"🧪 DRY_RUN: {dry_run_label}",
        f"🏦 Режим: {mode_label}",
        f"🛡 Kill-switch: {kill_line}",
        f"⏱ Uptime: {uptime}",
        f"⏯ Торговля: {bot_running}",
    ]

    inline: list[list[dict[str, Any]]] = [
        [
            {"text": "🧪 Переключить DRY_RUN", "callback_data": CB_TOGGLE_DRY_RUN},
            {"text": "🤖 Режим AI-Gate", "callback_data": CB_AIGATE_MENU},
        ],
        [
            {"text": "🏦 Демо/Реал", "callback_data": CB_MODE_SWITCH},
        ],
    ]
    if kill_state != "NONE":
        inline.append(
            [{"text": "🆘 Снять kill-switch", "callback_data": CB_KILL_CLEAR}]
        )
    inline.append([{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}])

    return "\n".join(lines), {"inline_keyboard": inline}


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
        return "💼 Открытых позиций нет."

    # Сортировка по PnL abs по убыванию.
    positions.sort(key=lambda p: p["pnl_abs"], reverse=True)

    now = datetime.now(tz=timezone.utc)
    lines = ["📈 <b>Открытые позиции</b>", ""]
    for p in positions:
        is_long = p["side"] == "Buy"
        side_emoji = "🟢" if is_long else "🔴"
        side_label = "LONG" if is_long else "SHORT"
        entry_ts = _parse_iso(p["entry_ts_iso"])
        hold = (
            _format_uptime((now - entry_ts).total_seconds())
            if entry_ts else "-"
        )
        # Прогресс к TP: TP у нас не жёсткий (trailing), показываем nan.
        # Безопаснее не показывать строку, чем обмануть пользователя.
        lines.append(
            f"{side_emoji} <b>{p['symbol']}</b> {side_label}\n"
            f"   вход: {p['entry']:.4f} → сейчас: {p['cur']:.4f}\n"
            f"   PnL: {p['pnl_abs']:+.2f} USDT ({p['pnl_pct']:+.2f}%)\n"
            f"   время: {hold}\n"
            f"   стоп: {p['stop']:.4f} ({p['stop_pct']:+.2f}% от входа)"
        )
        lines.append("")
    return "\n".join(lines).rstrip()


async def _handle_regimes(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Режимы рынка по 7 символам + последнее обновление."""
    lines = ["🎯 <b>Режимы рынка</b>", ""]
    last_ts: Optional[datetime] = None
    for symbol in config.SYMBOLS:
        sym_state = (state.get("symbols") or {}).get(symbol) or {}
        regime = sym_state.get("regime") or {}
        r_name = str(regime.get("regime") or "-")
        conf = regime.get("confidence")
        reason = str(regime.get("reason") or "").strip()
        if len(reason) > 80:
            reason = reason[:77] + "..."
        ts = _parse_iso(regime.get("ts"))
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts
        emoji = _regime_emoji(r_name)
        conf_str = f"{int(conf)}" if conf is not None else "?"
        lines.append(
            f"{emoji} <b>{symbol}</b> - {_ru_regime(r_name)} (уверенность {conf_str})"
        )
        if reason:
            lines.append(f"   «{reason}»")
        lines.append("")
    if last_ts:
        lines.append(
            f"🕐 Последнее обновление: {last_ts.strftime('%H:%M UTC')}"
        )
    return "\n".join(lines).rstrip()


async def _handle_aigate(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Меню AI-Gate: статус + статистика 24ч/7д + топ причин + inline-действия."""
    gate_mode_raw = str(
        getattr(config, "AI_TRADE_GATE_MODE", "off") or "off"
    ).lower()
    gate_mode_ru = {
        "active": "активен (строгая защита)",
        "shadow": "наблюдение (без блокировки)",
        "off": "выключен",
    }.get(gate_mode_raw, gate_mode_raw)

    try:
        stats24 = memory.get_ai_gate_stats(24)
        stats7d = memory.get_ai_gate_stats(24 * 7)
        top_reasons = memory.get_ai_gate_top_veto_reasons(24 * 7, limit=5)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] AI-Gate stats ошибка: {exc}")
        stats24 = {"approve": 0, "veto": 0, "error": 0, "total": 0, "applied": 0}
        stats7d = dict(stats24)
        top_reasons = []

    lines = [
        f"🛡 <b>AI-Gate</b>: {gate_mode_ru}",
        "",
        "📊 За 24 часа:",
        f"   ✅ одобрено:  {stats24['approve']}",
        f"   🚫 veto:      {stats24['veto']}",
        f"   ⚠ ошибка:    {stats24['error']}",
        f"   Всего:       {stats24['total']}",
        "",
        "📅 За 7 дней:",
        f"   ✅ {stats7d['approve']} / 🚫 {stats7d['veto']} / ⚠ {stats7d['error']}",
        "",
        "🎯 Топ причин блокировки (7 дней):",
    ]
    if top_reasons:
        for i, r in enumerate(top_reasons, start=1):
            reason = str(r.get("reason") or "-")
            if len(reason) > 80:
                reason = reason[:77] + "..."
            lines.append(f"   {i}. {reason} ({r['count']})")
    else:
        lines.append("   (блокировок за 7 дней нет)")

    # Inline-кнопки: адаптивно под текущий режим.
    inline: list[list[dict[str, Any]]] = []
    if gate_mode_raw == "active":
        inline.append([
            {"text": "🔀 Переключить в наблюдение",
             "callback_data": CB_AIGATE_SET_SHADOW},
        ])
        inline.append([
            {"text": "🔀 Выключить AI-Gate",
             "callback_data": CB_AIGATE_SET_OFF},
        ])
    elif gate_mode_raw == "shadow":
        inline.append([
            {"text": "🔀 Включить защиту (active)",
             "callback_data": CB_AIGATE_SET_ACTIVE},
        ])
        inline.append([
            {"text": "🔀 Выключить AI-Gate",
             "callback_data": CB_AIGATE_SET_OFF},
        ])
    else:  # off
        inline.append([
            {"text": "🔀 Включить защиту (active)",
             "callback_data": CB_AIGATE_SET_ACTIVE},
        ])
        inline.append([
            {"text": "🔀 Включить наблюдение (shadow)",
             "callback_data": CB_AIGATE_SET_SHADOW},
        ])
    inline.append([
        {"text": "📜 Последние 10 решений",
         "callback_data": CB_AIGATE_RECENT},
    ])
    inline.append([{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}])

    return "\n".join(lines), {"inline_keyboard": inline}


async def _handle_aigate_recent(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Последние 10 решений AI-Gate."""
    try:
        recs = memory.get_ai_gate_recent(10)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_ai_gate_recent: {exc}")
        recs = []
    if not recs:
        return "📜 Решений AI-Gate пока нет."
    lines = ["📜 <b>Последние решения AI-Gate</b>", ""]
    for r in recs:
        ts = _parse_iso(r.get("ts"))
        ts_s = ts.strftime("%d.%m %H:%M") if ts else (r.get("ts") or "-")
        symbol = r.get("symbol") or "-"
        side = r.get("side") or "-"
        verdict_ru = _ru_verdict(r.get("verdict") or "")
        applied_mark = " ✅" if r.get("applied") else ""
        conf = r.get("confidence")
        conf_s = f" conf={int(conf)}" if conf is not None else ""
        reason = str(r.get("reason") or "").strip()
        if len(reason) > 100:
            reason = reason[:97] + "..."
        lines.append(
            f"• {ts_s} {symbol} {side}: {verdict_ru}{applied_mark}{conf_s}"
        )
        if reason:
            lines.append(f"   «{reason}»")
    return "\n".join(lines)


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

    lines = ["🔍 <b>Отклонённые сигналы</b>", ""]
    total = sum(c["count"] for c in counts)
    lines.append(f"📊 За последние 24ч отклонено {total} сигналов:")
    if counts:
        for c in counts:
            lines.append(
                f"   • {_ru_filter_tag(c['filter'])}: {c['count']}"
            )
    else:
        lines.append("   (отклонений нет)")
    lines.append("")

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
        lines.append(f"🕐 Последнее ({minutes_ago} мин назад):")
        lines.append(f"   {symbol} → {_ru_filter_tag(flt)}")
        if detail:
            lines.append(f"   «{detail}»")
    else:
        lines.append("🕐 Последнее: отклонений не было")

    inline = {
        "inline_keyboard": [
            [{"text": "🤖 Спросить AI-аналитика",
              "callback_data": CB_WHY_AI}],
            [{"text": "🛡 Только AI-Gate блокировки",
              "callback_data": CB_WHY_GATE_ONLY}],
            [{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return "\n".join(lines), inline


async def _handle_why_ai(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    try:
        last = memory.get_last_rejected_check()
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] get_last_rejected_check: {exc}")
        last = None
    if not last:
        return "🤖 Отклонений пока нет - разбирать нечего."
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
    return (
        f"🤖 <b>AI-разбор последнего отклонения</b>\n\n"
        f"Символ: {symbol}\n"
        f"Фильтр: {_ru_filter_tag(flt)}\n\n"
        f"{explanation}"
    )


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
    lines = ["🛡 <b>AI-Gate блокировки (24ч)</b>", ""]
    total = sum(c["count"] for c in gate_counts)
    if not gate_counts:
        lines.append("За 24 часа AI-Gate не блокировал сделок.")
    else:
        lines.append(f"Всего: {total}")
        for c in gate_counts:
            lines.append(
                f"   • {_ru_filter_tag(c['filter'])}: {c['count']}"
            )
    return "\n".join(lines)


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

    title = {
        "errors": "📝 <b>Логи (только ошибки)</b>",
        "aigate": "📝 <b>Логи (только AI-GATE)</b>",
        "base": "📝 <b>Логи (последние 40 строк)</b>",
    }.get(variant, "📝 <b>Логи</b>")

    msg = f"{title}\n\n<pre>{text}</pre>"

    inline = {
        "inline_keyboard": [
            [
                {"text": "🔄 Обновить", "callback_data": CB_LOGS_REFRESH},
            ],
            [
                {"text": "🔍 Только ошибки", "callback_data": CB_LOGS_ERRORS},
                {"text": "🛡 Только AI-Gate", "callback_data": CB_LOGS_AIGATE},
            ],
            [{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}],
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
    status_s = "🟢 запущен" if bot_running else "🔴 на паузе"
    dry_label = "ВКЛ" if getattr(config, "DRY_RUN", False) else "ВЫКЛ"
    text = (
        "⏯ <b>Старт/Стоп · 🚨 PANIC SELL</b>\n\n"
        f"<b>Старт / Стоп</b>\n"
        f"Статус: {status_s}\n"
        f"DRY_RUN: {dry_label}\n\n"
        f"<b>Panic Sell</b>\n"
        f"Закрытие всех открытых позиций reduce-only маркетом\n"
        f"и пауза торговли. Подтверждение в два шага."
    )
    inline = {
        "inline_keyboard": [
            [
                {"text": "⏯ Старт / Стоп", "callback_data": CB_STARTSTOP},
                {"text": "🚨 PANIC SELL", "callback_data": CB_PANIC},
            ],
            [{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}],
        ]
    }
    return text, inline


async def _handle_analyst(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Заглушка кнопки 🤖 АНАЛИТИК (FEAT-007 / C3)."""
    return "Аналитик появится в этапе C3"


async def _handle_startstop_menu(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    g = _g(state)
    bot_running = bool(g.get("bot_running", True))
    status_s = "🟢 запущен" if bot_running else "🔴 на паузе"
    dry_label = "ВКЛ" if getattr(config, "DRY_RUN", False) else "ВЫКЛ"
    text = (
        "⏯ <b>Старт / Стоп</b>\n\n"
        f"Статус: {status_s}\n"
        f"Режим DRY_RUN: {dry_label}"
    )
    dry_btn_text = (
        "⚠ Выключить DRY_RUN"
        if getattr(config, "DRY_RUN", False)
        else "🧪 Включить DRY_RUN"
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
    inline.append([{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}])
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
        "active": "активен (строгая защита)",
        "shadow": "наблюдение (без блокировки)",
        "off": "выключен",
    }.get(new_mode, new_mode)
    current_ru = {
        "active": "активен (строгая защита)",
        "shadow": "наблюдение (без блокировки)",
        "off": "выключен",
    }.get(current, current)
    text = (
        "🛡 <b>Переключение AI-Gate</b>\n\n"
        f"Сейчас: {current_ru}\n"
        f"Станет: {target_ru}\n\n"
        "Подтвердить?"
    )
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
        return f"⚠ Не удалось переключить AI-Gate: {result}"
    return (
        f"✅ AI-Gate переключён в режим <b>{result}</b>.\n"
        f"Значение применено сразу (без рестарта) и сохранено в .env."
    )


# --- PANIC SELL (two-step confirm) -----------------------------------------

async def _handle_panic(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    text = (
        "🚨 <b>PANIC SELL - подтверждение</b>\n\n"
        "Будут закрыты <b>все открытые позиции</b> по "
        f"{', '.join(config.SYMBOLS)} reduce-only маркетом, "
        "и торговля будет поставлена на паузу.\n\n"
        "Вы уверены?"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚠ ДА, ЗАКРЫТЬ ВСЁ", "callback_data": CB_PANIC_CONFIRM},
                {"text": "❌ Отмена", "callback_data": CB_PANIC_CANCEL},
            ],
        ]
    }
    return text, keyboard


async def _handle_panic_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = False
    if getattr(config, "DRY_RUN", False):
        return (
            "[DRY RUN] 🚨 PANIC SELL имитация: реальные ордера не отправлены. "
            "Торговля поставлена на паузу."
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
        return "🚨 PANIC SELL: открытых позиций не было. Торговля поставлена на паузу."
    return (
        f"🚨 PANIC SELL выполнен: отправлено {total_orders} ордеров на закрытие "
        f"по {len(config.SYMBOLS)} символам. Торговля поставлена на паузу."
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
    current_ru = (
        "ДЕМО (OKX testnet, виртуальные 5000 USDT)"
        if is_testnet_now
        else "⚠ РЕАЛ (OKX mainnet, реальные деньги)"
    )
    target_ru = (
        "⚠ РЕАЛ (OKX mainnet, реальные деньги)"
        if is_testnet_now
        else "ДЕМО (OKX testnet, виртуальные 5000 USDT)"
    )

    # Открытые позиции предупреждение.
    open_count = sum(
        1 for s in state.get("symbols", {}).values() if s.get("open_trade")
    )
    open_warn = ""
    if open_count > 0:
        account_label = "демо" if is_testnet_now else "реал"
        open_warn = (
            f"\n\n⚠ Сейчас открыто позиций ({open_count}) на {account_label}-счёте. "
            f"После переключения они останутся на {account_label}-аккаунте, "
            f"но бот их НЕ сможет управлять (ключи поменяются).\n"
            f"Рекомендуется сначала закрыть позиции через 🚨 PANIC SELL."
        )

    # Проверка заполненности целевых ключей.
    keys_warn = ""
    if is_testnet_now:
        # Переходим на mainnet - нужны real-ключи.
        if not config.OKX_API_KEY_REAL:
            keys_warn = (
                "\n\n❌ <b>Реал-ключи не заполнены</b>\n"
                "В .env нет OKX_API_KEY_REAL (или он пустой). Без реал-ключей "
                "бот не сможет авторизоваться на OKX mainnet.\n"
                "Заполните через: 🔑 КЛЮЧИ API → OKX Real *"
            )
    else:
        # Переходим на demo - нужны demo-ключи.
        if not config.OKX_API_KEY_DEMO:
            keys_warn = (
                "\n\n❌ <b>Демо-ключи не заполнены</b>\n"
                "В .env нет OKX_API_KEY (демо). Без них бот не сможет "
                "авторизоваться на OKX testnet.\n"
                "Заполните через: 🔑 КЛЮЧИ API → OKX Demo *"
            )

    # Специальное предупреждение при переходе на РЕАЛ.
    real_warn = ""
    if is_testnet_now:
        real_warn = (
            "\n\n⚠⚠⚠ <b>ВНИМАНИЕ</b> ⚠⚠⚠\n\n"
            "Это переключение на боевой счёт с реальными деньгами. "
            "Все сделки будут исполняться на ваш реальный OKX-аккаунт.\n\n"
            "Убедитесь что:\n"
            "• OKX_API_KEY_REAL / _SECRET_REAL / _PASSPHRASE_REAL заполнены "
            "(🔑 КЛЮЧИ API → OKX Real *)\n"
            "• Открытых позиций на демо сейчас нет (или готовы оставить их на демо)"
        )

    text = (
        "🏦 <b>Переключение режима торговли</b>\n\n"
        f"Сейчас: {current_ru}\n"
        f"Станет: {target_ru}"
        + real_warn
        + open_warn
        + keys_warn
    )

    # Если целевые ключи пусты - кнопку «Да» не показываем.
    inline_rows: list[list[dict[str, Any]]] = []
    if keys_warn:
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
        "⚠ РЕАЛ (OKX mainnet)" if is_testnet_now else "ДЕМО (OKX testnet)"
    )
    if not _write_env_var("IS_TESTNET", new_val):
        return "⚠ Не удалось записать IS_TESTNET в .env. Переключение отменено."
    asyncio.get_event_loop().call_later(1.0, _self_terminate)
    return (
        f"✅ Переключение на <b>{target_label}</b> сохранено в .env.\n"
        f"Бот перезапускается... (~20 секунд)"
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
    text = (
        "🔑 <b>Замена ключей API</b>\n\n"
        "⚠ Внимание:\n"
        "• Сообщение с новым ключом бот удалит автоматически\n"
        "• После замены бот перезапустится (~20 секунд)\n\n"
        "▼ OKX Демо (активны при IS_TESTNET=true):\n"
        "▼ OKX Реал (активны при IS_TESTNET=false):\n"
        "▼ Общие для всех режимов."
    )
    rows: list[list[dict[str, Any]]] = []
    for ui_name, env_name, emoji in _KEY_UI_NAMES:
        rows.append([{
            "text": f"{emoji} {ui_name}",
            "callback_data": f"{CB_KEY_PREFIX}{env_name}",
        }])
    rows.append([{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}])
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
            f"⚠ Сейчас открыто {open_count} демо-позиций. После замены "
            f"демо-ключа бот потеряет с ними связь.\n"
            f"Рекомендуется сначала закрыть через 🚨 PANIC SELL."
        )
    if is_okx_real and (not config.IS_TESTNET) and open_count > 0:
        warnings.append(
            f"⚠⚠⚠ Сейчас открыто {open_count} РЕАЛ-позиций. После замены "
            f"реал-ключа бот потеряет с ними связь, они останутся на "
            f"бирже без управления.\n"
            f"Строго рекомендуется сначала закрыть через 🚨 PANIC SELL."
        )
    if env_name == "TELEGRAM_TOKEN":
        warnings.append(
            "⚠⚠⚠ <b>КРИТИЧНО</b>: смена TELEGRAM_TOKEN приведёт к тому, "
            "что этот чат потеряет связь с ботом. Восстановление возможно "
            "только через SSH на сервер (правка /opt/zenith/.env)."
        )

    # Переводим FSM в состояние «ждём значение».
    _key_fsm_state[chat_id] = {
        "env_name": env_name,
        "pending_value": None,
        "started": time.time(),
    }

    lines = [f"🔑 <b>Замена: {ui_name}</b>"]
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(w)
    lines.append("")
    lines.append("Пришлите новое значение ОДНИМ сообщением.")
    lines.append("Бот удалит ваше сообщение сразу после получения.")
    lines.append("")
    lines.append("У вас есть 5 минут.")

    inline = {
        "inline_keyboard": [
            [{"text": "❌ Отмена", "callback_data": CB_KEY_CANCEL}],
        ]
    }
    return "\n".join(lines), inline


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
            [{"text": "◀ Главное меню", "callback_data": CB_BACK_MAIN}],
        ]
    }

    if snap.get("updated_epoch", 0.0) == 0.0:
        text = (
            "🤖 <b>Квота Groq API</b>\n\n"
            "⏱ Снапшот квоты ещё не получен.\n\n"
            "Дождитесь первого вызова Groq "
            "(macro-sentinel / ai_regime / AI-Gate) — обычно это "
            "происходит в течение минуты после старта."
        )
        return text, inline

    age_sec = int(max(0, time.time() - snap["updated_epoch"]))
    if age_sec < 60:
        age_str = f"{age_sec}с назад"
    elif age_sec < 3600:
        age_str = f"{age_sec // 60}м назад"
    else:
        age_str = f"{age_sec // 3600}ч {(age_sec % 3600) // 60}м назад"

    def _pct(used: int, limit: int) -> str:
        if limit <= 0:
            return "0.0%"
        return f"{(used / limit) * 100.0:.1f}%"

    rpd_used = max(0, snap["rpd_limit"] - snap["rpd_remaining"])
    tpd_used = max(0, snap["tpd_limit"] - snap["tpd_remaining"])
    rpm_used = max(0, snap["rpm_limit"] - snap["rpm_remaining"])

    lines = [
        "🤖 <b>Квота Groq API</b>",
        "",
        "📊 Сегодня:",
        f"   ✅ Запросов: {rpd_used} / {snap['rpd_limit']} ({_pct(rpd_used, snap['rpd_limit'])})",
        f"   🔵 Токенов:  {tpd_used} / {snap['tpd_limit']} ({_pct(tpd_used, snap['tpd_limit'])})",
        "",
        "⏱ Текущая минута:",
        f"   Запросов: {rpm_used} / {snap['rpm_limit']} ({_pct(rpm_used, snap['rpm_limit'])})",
    ]

    reset_lines = []
    if snap.get("rpd_reset"):
        reset_lines.append(f"   Запросы (сутки): {snap['rpd_reset']}")
    if snap.get("tpd_reset"):
        reset_lines.append(f"   Токены (сутки):  {snap['tpd_reset']}")
    if snap.get("rpm_reset"):
        reset_lines.append(f"   Минутный лимит:  {snap['rpm_reset']}")
    if reset_lines:
        lines.append("")
        lines.append("🔄 Квота сбрасывается через:")
        lines.extend(reset_lines)

    lines.append("")
    lines.append(f"📡 Снапшот обновлён: {age_str}")
    lines.append("")
    lines.append("💡 Ориентировочное потребление:")
    lines.append("   • macro-sentinel: ~1 / час")
    lines.append("   • ai_regime:     ~14 / час (7 символов × 2 обновл.)")
    lines.append("   • ai_trade_gate: 0-5 / час (зависит от сигналов)")
    lines.append("   Итого ≈ 360-480 вызовов в сутки")

    return "\n".join(lines), inline


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
