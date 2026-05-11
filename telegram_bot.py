"""Telegram-терминал для Zenith-Control Ultimate.

Long polling через aiohttp напрямую (без python-telegram-bot).
СТРОГО: каждое сообщение и callback_query, у которого from.id или chat.id
не равен TELEGRAM_CHAT_ID, отбрасывается молча. На callback_query чужого
пользователя отвечаем answerCallbackQuery с текстом «Доступ запрещён»,
но ничего в системе не меняем.

Шесть inline-кнопок:
  ▶️ СТАРТ, ⏸ СТОП, 📊 СТАТИСТИКА, 📂 ПОЗИЦИИ, 🚨 PANIC SELL, 🧠 ПОЧЕМУ МИМО?
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import aiohttp

import ai_analyst
import api_engine
import config
import memory


# --- Callback data ids (короткие, чтобы влезали в ограничение Telegram 64 байта) ---
CB_START = "zc:start"
CB_STOP = "zc:stop"
CB_STATS = "zc:stats"
CB_POSITIONS = "zc:positions"
CB_PANIC = "zc:panic"
CB_WHY = "zc:why"


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


def set_keyboard() -> dict[str, Any]:
    """Инлайн-клавиатура с 6 кнопками."""
    return {
        "inline_keyboard": [
            [
                {"text": "▶️ СТАРТ", "callback_data": CB_START},
                {"text": "⏸ СТОП", "callback_data": CB_STOP},
            ],
            [
                {"text": "📊 СТАТИСТИКА", "callback_data": CB_STATS},
                {"text": "📂 ПОЗИЦИИ", "callback_data": CB_POSITIONS},
            ],
            [
                {"text": "🚨 PANIC SELL", "callback_data": CB_PANIC},
                {"text": "🧠 ПОЧЕМУ МИМО?", "callback_data": CB_WHY},
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
            # chat_id может отсутствовать у старых сообщений - достаточно from.id.
            if chat_id is None:
                return from_id == allowed
            return from_id == allowed and chat_id == allowed
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка проверки авторизации: {exc}")
    return False


# --- Обработчики кнопок ---

async def _handle_start(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    state["bot_running"] = True
    return "✅ Торговля <b>запущена</b>. Бот снова ищет сигналы."


async def _handle_stop(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    state["bot_running"] = False
    return "⏸ Торговля <b>остановлена</b>. Открытые позиции продолжают управляться."


async def _handle_stats(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    stats = memory.get_stats()
    daily_pnl = state.get("daily_pnl", 0.0) or 0.0
    status = "включен" if state.get("bot_running") else "на паузе"
    return (
        "📊 <b>Статистика</b>\n"
        f"Статус: {status}\n"
        f"Всего закрытых сделок: {stats['count']}\n"
        f"Победы: {stats['wins']}, Убытки: {stats['losses']}\n"
        f"Винрейт: {stats['winrate']:.2f}%\n"
        f"Суммарный PnL: {stats['pnl_sum']:.4f}\n"
        f"PnL за сегодня: {daily_pnl:.4f}"
    )


async def _handle_positions(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    # Реальные позиции с биржи + локальные OPEN-сделки для контекста.
    remote: list[dict[str, Any]] = []
    try:
        remote = await api_engine.get_positions(session, config.SYMBOL)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка get_positions: {exc}")
    local = memory.get_open_trades()

    lines = ["📂 <b>Открытые позиции</b>"]
    if remote:
        for p in remote:
            lines.append(
                f"• {p.get('symbol')} {p.get('side')} size={p.get('size')} "
                f"entry={p.get('avgPrice')} uPnL={p.get('unrealisedPnl')}"
            )
    else:
        lines.append("• на бирже позиций нет")
    if local:
        lines.append("")
        lines.append("Локальные записи (OPEN):")
        for t in local:
            lines.append(
                f"• #{t['id']} {t['symbol']} {t['side']} qty={t['qty']} entry={t['entry']}"
            )
    return "\n".join(lines)


async def _handle_panic(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    state["bot_running"] = False
    results = await api_engine.panic_sell(session, config.SYMBOL)
    if not results:
        return "🚨 PANIC SELL: открытых позиций не было. Торговля поставлена на паузу."
    return (
        f"🚨 PANIC SELL выполнен: отправлено {len(results)} ордеров на закрытие. "
        "Торговля поставлена на паузу."
    )


async def _handle_why(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    last = memory.get_last_rejection()
    if not last:
        return "🧠 Отклонённых сигналов пока нет."
    errors = memory.get_recent_errors(5)
    explanation = await ai_analyst.explain_last_rejection(session, last, errors)
    return (
        "🧠 <b>ПОЧЕМУ МИМО?</b>\n"
        f"Дата: {last.get('ts')}\n"
        f"Причина модели: {last.get('reason')}\n"
        f"Уверенность: {last.get('confidence')}\n\n"
        f"Разбор: {explanation}"
    )


_HANDLERS = {
    CB_START: _handle_start,
    CB_STOP: _handle_stop,
    CB_STATS: _handle_stats,
    CB_POSITIONS: _handle_positions,
    CB_PANIC: _handle_panic,
    CB_WHY: _handle_why,
}


async def _process_callback(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    cb: dict[str, Any],
) -> None:
    cb_id = cb.get("id")
    data = cb.get("data", "")
    handler = _HANDLERS.get(data)
    if not handler:
        if cb_id:
            await answer_callback(session, cb_id, "Неизвестная команда")
        return
    try:
        text = await handler(session, state)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка обработчика {data}: {exc}")
        text = f"Ошибка обработчика: {exc}"
    if cb_id:
        await answer_callback(session, cb_id, "Готово")
    await send_message(session, text, reply_markup=set_keyboard())


async def _process_message(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    msg: dict[str, Any],
) -> None:
    text = (msg.get("text") or "").strip()
    if text.lower() in ("/start", "/menu", "/help"):
        await send_message(
            session,
            "👋 <b>Zenith-Control Ultimate</b>\nВыберите действие кнопкой ниже.",
            reply_markup=set_keyboard(),
        )
        return
    if text.lower() == "/status":
        await send_message(
            session,
            await _handle_stats(session, state),
            reply_markup=set_keyboard(),
        )
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
        # Чтобы asyncio.gather не завершился мгновенно, просто спим.
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
                # Молчаливый дроп сообщений; на callback от чужих отвечаем «Доступ запрещён».
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
