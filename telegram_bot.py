"""Telegram-терминал для Zenith-Control Ultimate v2.

Long polling через aiohttp напрямую (без python-telegram-bot).
СТРОГО: каждое сообщение и callback_query, у которого from.id или chat.id
не равен TELEGRAM_CHAT_ID, отбрасывается молча. На callback_query чужого
пользователя отвечаем answerCallbackQuery с текстом «Доступ запрещён»,
но ничего в системе не меняем.

Десять inline-кнопок:
  ▶️ СТАРТ, ⏸ СТОП,
  📊 СТАТИСТИКА, 📂 ПОЗИЦИИ,
  🚨 PANIC SELL, 🧠 ПОЧЕМУ МИМО?,
  📈 ОТЧЁТ, 🎚 РЕЖИМЫ,
  🛡 KILL-STATE, ✅ СНЯТЬ MDD.

Состояние state в v2 имеет форму:
    {
      'symbols': {symbol: {...}},
      'global': {...},
      'instruments': {...},
    }
Для обратной совместимости с v1-тестами (где state плоский) читаем
`state['global']['bot_running']` с fallback'ом на `state['bot_running']`.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

import ai_analyst
import ai_postmortem
import api_engine  # noqa: F401  # legacy shim
import arbitrage_engine
import config
import memory
from exchanges import get_adapter


# Единый адаптер биржи (выбирается через config.EXCHANGE).
EXCHANGE = get_adapter(config.EXCHANGE)


# Адаптеры для funding-сканера. Те же экземпляры, что в main.py, но в
# рамках этого модуля собираем свой набор - чтобы /arb можно было
# вызвать ad-hoc даже до первого _funding_scan_tick (например на
# свежезапущенном боте).
_FUNDING_ADAPTERS: dict[str, Any] = {}
for _ex_name in getattr(config, "FUNDING_SCAN_EXCHANGES", ()):
    try:
        _FUNDING_ADAPTERS[_ex_name] = get_adapter(_ex_name)
    except Exception as _exc:  # noqa: BLE001
        print(f"[TG] Funding-адаптер {_ex_name} недоступен: {_exc}")


# --- Callback data ids (короткие, чтобы влезали в ограничение Telegram 64 байта) ---
CB_START = "zc:start"
CB_STOP = "zc:stop"
CB_STATS = "zc:stats"
CB_POSITIONS = "zc:positions"
CB_PANIC = "zc:panic"
CB_WHY = "zc:why"
CB_REPORT = "zc:report"
CB_REGIMES = "zc:regimes"
CB_KILL = "zc:kill"
CB_RESUME_MDD = "zc:resume_mdd"

# Двухэтапное подтверждение опасных действий (PANIC SELL и снятие MDD).
# Основная кнопка (CB_PANIC / CB_RESUME_MDD) не выполняет действие,
# а показывает диалог с двумя кнопками: подтвердить или отменить.
CB_PANIC_CONFIRM = "zc:panic_ok"
CB_PANIC_CANCEL = "zc:panic_no"
CB_RESUME_MDD_CONFIRM = "zc:mdd_ok"
CB_RESUME_MDD_CANCEL = "zc:mdd_no"


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


def _g(state: dict[str, Any]) -> dict[str, Any]:
    """Вернуть словарь «глобального» раздела state.

    В v2 это `state['global']`. Для обратной совместимости с плоским
    v1-словарём (где `bot_running` лежал прямо в state) возвращаем сам state.
    """
    g = state.get("global") if isinstance(state, dict) else None
    if isinstance(g, dict):
        return g
    return state


def set_keyboard() -> dict[str, Any]:
    """Инлайн-клавиатура с 10 кнопками (5 строк по 2)."""
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
            [
                {"text": "📈 ОТЧЁТ", "callback_data": CB_REPORT},
                {"text": "🎚 РЕЖИМЫ", "callback_data": CB_REGIMES},
            ],
            [
                {"text": "🛡 KILL-STATE", "callback_data": CB_KILL},
                {"text": "✅ СНЯТЬ MDD", "callback_data": CB_RESUME_MDD},
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


# --- Обработчики кнопок ---

async def _handle_start(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = True
    return "✅ Торговля <b>запущена</b>. Бот снова ищет сигналы."


async def _handle_stop(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = False
    return "⏸ Торговля <b>остановлена</b>. Открытые позиции продолжают управляться."


async def _handle_stats(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    stats = memory.get_stats()
    g = _g(state)
    daily_pnl = float(g.get("daily_pnl", 0.0) or 0.0)
    weekly_pnl = float(g.get("weekly_pnl", 0.0) or 0.0)
    status = "включен" if g.get("bot_running", True) else "на паузе"
    return (
        "📊 <b>Статистика</b>\n"
        f"Статус: {status}\n"
        f"Всего закрытых сделок: {stats['count']}\n"
        f"Победы: {stats['wins']}, Убытки: {stats['losses']}\n"
        f"Винрейт: {stats['winrate']:.2f}%\n"
        f"Суммарный PnL: {stats['pnl_sum']:.4f}\n"
        f"PnL за сегодня: {daily_pnl:.4f}\n"
        f"PnL за неделю: {weekly_pnl:.4f}"
    )


async def _handle_positions(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    # Реальные позиции по всем символам + локальные OPEN-сделки для контекста.
    remote: list[dict[str, Any]] = []
    for sym in config.SYMBOLS:
        try:
            chunk = await EXCHANGE.get_positions(session, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] Ошибка get_positions({sym}): {exc}")
            chunk = []
        if chunk:
            remote.extend(chunk)
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
) -> tuple[str, dict[str, Any]]:
    """Первый шаг: показать диалог подтверждения, позиции НЕ трогаем.

    Возвращает (текст, клавиатура). Реальное исполнение - в _handle_panic_confirm
    при нажатии кнопки «⚠️ ДА, ЗАКРЫТЬ ВСЁ».
    """
    text = (
        "🚨 <b>PANIC SELL — подтверждение</b>\n\n"
        "Будут закрыты <b>все открытые позиции</b> по "
        f"{', '.join(config.SYMBOLS)} reduce-only маркетом, "
        "и торговля будет поставлена на паузу.\n\n"
        "Вы уверены?"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚠️ ДА, ЗАКРЫТЬ ВСЁ", "callback_data": CB_PANIC_CONFIRM},
                {"text": "Отмена", "callback_data": CB_PANIC_CANCEL},
            ]
        ]
    }
    return text, keyboard


async def _handle_panic_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Второй шаг: реально закрываем все позиции и ставим торговлю на паузу."""
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


async def _handle_why(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    last: Optional[dict[str, Any]] = None
    g = _g(state)
    ring = g.get("rejection_ring")
    if ring:
        try:
            last = dict(ring[-1])  # последний элемент deque
        except (IndexError, TypeError, ValueError):
            last = None
    if last is None:
        try:
            last = memory.get_last_rejected_check()
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] Ошибка get_last_rejected_check: {exc}")
            last = None
    if not last:
        return "🧠 Отклонённых сигналов пока нет."

    try:
        errors = memory.get_recent_errors(5)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка get_recent_errors: {exc}")
        errors = []
    try:
        explanation = await ai_analyst.explain_last_rejection(session, last, errors)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] explain_last_rejection: {exc}")
        explanation = "Объяснение временно недоступно."

    header = "🧠 <b>ПОЧЕМУ МИМО?</b>"
    ts = last.get("ts") or "-"
    symbol = last.get("symbol") or "-"
    filt = last.get("filter") or last.get("reason") or "-"
    detail = last.get("detail") or ""
    return (
        f"{header}\n"
        f"Дата: {ts}\n"
        f"Символ: {symbol}\n"
        f"Фильтр: {filt}\n"
        f"Детали: {detail}\n\n"
        f"Разбор: {explanation}"
    )


async def _handle_report(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    try:
        text = await ai_postmortem.report(session, days=7)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка ai_postmortem.report: {exc}")
        text = "Отчёт временно недоступен."
    text = (text or "Отчёт временно недоступен.").strip()
    if len(text) > 3800:
        text = text[:3800].rstrip()
    return "📈 <b>Еженедельный отчёт</b>\n\n" + text


async def _handle_regimes(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    symbols = state.get("symbols") if isinstance(state, dict) else None
    if not isinstance(symbols, dict) or not symbols:
        return "🎚 Данных о режимах пока нет."
    lines = ["🎚 <b>Режимы по символам</b>"]
    for symbol in config.SYMBOLS:
        sym_state = symbols.get(symbol) or {}
        regime = sym_state.get("regime") or {}
        regime_name = str(regime.get("regime") or "-")
        conf = regime.get("confidence")
        ts = regime.get("ts")
        if not ts:
            lines.append(f"• {symbol}: не опрошен")
            continue
        ts_dt = _parse_iso(ts)
        when = ts_dt.strftime("%H:%M UTC") if ts_dt else str(ts)
        conf_str = f"conf={conf}" if conf is not None else "conf=?"
        lines.append(
            f"• {symbol}: {regime_name} ({conf_str}, обновлено {when})"
        )
    return "\n".join(lines)


async def _handle_kill_state(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    g = _g(state)
    ks = str(g.get("kill_switch_state") or "NONE")
    until_iso = g.get("kill_until_utc")
    until_dt = _parse_iso(until_iso)
    remaining = _format_remaining(until_dt) if until_dt else "-"
    daily_pnl = float(g.get("daily_pnl", 0.0) or 0.0)
    weekly_pnl = float(g.get("weekly_pnl", 0.0) or 0.0)
    try:
        current_dd = float(memory.get_current_drawdown() or 0.0)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка get_current_drawdown: {exc}")
        current_dd = 0.0
    equity_start = g.get("equity_start")
    equity_line = (
        f"{float(equity_start):.4f}" if equity_start is not None else "не задан"
    )
    bot_running = "включен" if g.get("bot_running", True) else "на паузе"
    detail = str(g.get("kill_detail") or "")

    parts = [
        "🛡 <b>KILL-STATE</b>",
        f"Статус: {ks}",
        f"До снятия: {remaining}",
        f"Дедлайн: {until_iso or '-'}",
        f"Суточный PnL: {daily_pnl:.4f}",
        f"Недельный PnL: {weekly_pnl:.4f}",
        f"Текущая просадка: {current_dd * 100:.2f}%",
        f"Стартовое эквити: {equity_line}",
        f"Торговля: {bot_running}",
    ]
    if detail:
        parts.append(f"Причина: {detail}")
    return "\n".join(parts)


async def _handle_resume_mdd(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Первый шаг: показать диалог подтверждения, kill-switch НЕ трогаем."""
    g = _g(state)
    if g.get("kill_switch_state") != "MDD":
        # Нечего снимать - диалог не нужен, сразу ответ без кнопок.
        return (
            "✅ MDD не активен, сбрасывать нечего.",
            set_keyboard(),
        )
    text = (
        "✅ <b>СНЯТЬ MDD kill-switch — подтверждение</b>\n\n"
        "MDD активируется при просадке ≥ "
        f"{config.MAX_DRAWDOWN * 100:.0f}% от HWM и снимается ТОЛЬКО вручную. "
        "Убедитесь, что вы понимаете текущую просадку и готовы продолжить.\n\n"
        "Снять блокировку?"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ ДА, СНЯТЬ", "callback_data": CB_RESUME_MDD_CONFIRM},
                {"text": "Отмена", "callback_data": CB_RESUME_MDD_CANCEL},
            ]
        ]
    }
    return text, keyboard


async def _handle_resume_mdd_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Второй шаг: реально снимаем MDD (если он всё ещё активен)."""
    g = _g(state)
    if g.get("kill_switch_state") != "MDD":
        return "✅ MDD уже не активен."
    g["kill_switch_state"] = "NONE"
    g["kill_until_utc"] = None
    g["kill_detail"] = ""
    return "✅ MDD kill-switch снят вручную. Торговля возобновится при bot_running=on."


async def _handle_resume_mdd_cancel(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return "Отменено. MDD kill-switch остаётся активным."


async def _handle_arb(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Команда /arb (она же /funding) - снимок funding rate по всем
    настроенным биржам.

    Сначала пробуем взять кэшированный snapshot из state["global"]
    (его обновляет _funding_scan_tick раз в FUNDING_SCAN_INTERVAL_SEC).
    Если кэша ещё нет (старт процесса, тикер не успел отработать) -
    делаем ad-hoc-скан, чтобы пользователь увидел актуальные цифры.

    Все ошибки сети ловятся внутри scan_funding, наружу всплывают только
    в виде пустого результата - тогда показываем человеческое сообщение.
    """
    g = _g(state)
    snapshots = g.get("funding_snapshot")

    if not snapshots:
        if not _FUNDING_ADAPTERS:
            return (
                "📡 Сканер не настроен. Задайте config.FUNDING_SCAN_EXCHANGES "
                "и убедитесь, что адаптеры зарегистрированы."
            )
        try:
            snapshots = await arbitrage_engine.scan_funding(
                session, _FUNDING_ADAPTERS
            )
            g["funding_snapshot"] = snapshots
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] /arb: ошибка scan_funding: {exc}")
            return "Не удалось снять funding по биржам. Сетевая ошибка."

    if not any(snapshots.values()):
        return "📡 Funding-данных нет (все адаптеры вернули пусто)."

    return arbitrage_engine.format_full_report(snapshots)


_HANDLERS = {
    CB_START: _handle_start,
    CB_STOP: _handle_stop,
    CB_STATS: _handle_stats,
    CB_POSITIONS: _handle_positions,
    CB_PANIC: _handle_panic,
    CB_PANIC_CONFIRM: _handle_panic_confirm,
    CB_PANIC_CANCEL: _handle_panic_cancel,
    CB_WHY: _handle_why,
    CB_REPORT: _handle_report,
    CB_REGIMES: _handle_regimes,
    CB_KILL: _handle_kill_state,
    CB_RESUME_MDD: _handle_resume_mdd,
    CB_RESUME_MDD_CONFIRM: _handle_resume_mdd_confirm,
    CB_RESUME_MDD_CANCEL: _handle_resume_mdd_cancel,
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
        result = await handler(session, state)
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] Ошибка обработчика {data}: {exc}")
        result = f"Ошибка обработчика: {exc}"

    # Handler может вернуть либо str (текст + дефолтная клавиатура),
    # либо tuple (текст, кастомная клавиатура) - последнее используется
    # для диалогов подтверждения PANIC SELL и СНЯТЬ MDD.
    if isinstance(result, tuple) and len(result) == 2:
        text, keyboard = result
    else:
        text = result
        keyboard = set_keyboard()

    if cb_id:
        await answer_callback(session, cb_id, "Готово")
    await send_message(session, text, reply_markup=keyboard)


async def _process_message(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    msg: dict[str, Any],
) -> None:
    text = (msg.get("text") or "").strip()
    lowered = text.lower()
    if lowered in ("/start", "/menu", "/help"):
        await send_message(
            session,
            (
                "👋 <b>Zenith-Control Ultimate v2</b>\n"
                "Выберите действие кнопкой ниже.\n\n"
                "Доп. команды:\n"
                "<code>/arb</code> или <code>/funding</code> — funding rate "
                "по биржам (read-only сканер)\n"
                "<code>/status</code> — короткая статистика\n"
                "<code>/resume_kill_switch</code> — снять MDD"
            ),
            reply_markup=set_keyboard(),
        )
        return
    if lowered == "/status":
        await send_message(
            session,
            await _handle_stats(session, state),
            reply_markup=set_keyboard(),
        )
        return
    if lowered == "/resume_kill_switch":
        result = await _handle_resume_mdd(session, state)
        # Handler теперь возвращает либо str (MDD не активен), либо tuple
        # (текст, клавиатура подтверждения). Оба случая поддерживаем.
        if isinstance(result, tuple) and len(result) == 2:
            reply, keyboard = result
        else:
            reply = result
            keyboard = set_keyboard()
        await send_message(session, reply, reply_markup=keyboard)
        return
    if lowered in ("/arb", "/funding"):
        # Ответ может быть длинным (моноширинная таблица): сначала шлём
        # отчёт без клавиатуры, потом отдельно меню. Telegram <pre> блок
        # с клавиатурой иногда подрезается рендером.
        report = await _handle_arb(session, state)
        await send_message(session, report)
        await send_message(
            session,
            "Меню ниже.",
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
