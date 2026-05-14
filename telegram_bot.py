"""Telegram-терминал для Zenith-Control Ultimate v2 (Funding Arbitrage).

Long polling через aiohttp напрямую (без python-telegram-bot).
СТРОГО: каждое сообщение и callback_query, у которого from.id или chat.id
не равен TELEGRAM_CHAT_ID, отбрасывается молча. На callback_query чужого
пользователя отвечаем answerCallbackQuery с текстом «Доступ запрещён»,
но ничего в системе не меняем.

Восемь inline-кнопок (4 строки × 2):
  ▶️ СТАРТ, ⏸ СТОП,
  📊 СТАТИСТИКА, 📂 ПОЗИЦИИ,
  ⚡ АРБ СТАТУС, 📡 ФАНДИНГ,
  🚨 ЗАКРЫТЬ АРБ, 🛡 KILL-STATE,
  ✅ СНЯТЬ MDD.

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

import arb_executor
import arb_storage
import arbitrage_engine
import config
import key_manager
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
CB_START        = "zc:start"
CB_STOP         = "zc:stop"
CB_STATS        = "zc:stats"
CB_POSITIONS    = "zc:positions"
CB_ARB_STATUS   = "zc:arb"
CB_FUNDING      = "zc:fund"
CB_PANIC        = "zc:panic"
CB_KILL         = "zc:kill"
CB_RESUME_MDD   = "zc:resume_mdd"
CB_KEYS         = "zc:keys"
CB_EXCHANGES    = "zc:exchanges"

# Двухэтапное подтверждение опасных действий.
CB_PANIC_CONFIRM      = "zc:panic_ok"
CB_PANIC_CANCEL       = "zc:panic_no"
CB_RESUME_MDD_CONFIRM = "zc:mdd_ok"
CB_RESUME_MDD_CANCEL  = "zc:mdd_no"

# Префикс для toggle бирж: "zc:ext:" + exchange_name (e.g. "zc:ext:bitget")
CB_EX_TOGGLE_PREFIX = "zc:ext:"


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
    """Инлайн-клавиатура арб-бота (6 строк)."""
    return {
        "inline_keyboard": [
            [
                {"text": "▶️ СТАРТ", "callback_data": CB_START},
                {"text": "⏸ СТОП",  "callback_data": CB_STOP},
            ],
            [
                {"text": "📊 СТАТИСТИКА", "callback_data": CB_STATS},
                {"text": "📂 ПОЗИЦИИ",    "callback_data": CB_POSITIONS},
            ],
            [
                {"text": "⚡ АРБ СТАТУС", "callback_data": CB_ARB_STATUS},
                {"text": "📡 ФАНДИНГ",   "callback_data": CB_FUNDING},
            ],
            [
                {"text": "🚨 ЗАКРЫТЬ АРБ", "callback_data": CB_PANIC},
                {"text": "🛡 KILL-STATE",  "callback_data": CB_KILL},
            ],
            [
                {"text": "✅ СНЯТЬ MDD", "callback_data": CB_RESUME_MDD},
                {"text": "🔑 КЛЮЧИ",     "callback_data": CB_KEYS},
            ],
            [
                {"text": "🏦 БИРЖИ", "callback_data": CB_EXCHANGES},
            ],
        ]
    }


# Порядок отображения бирж в меню (все 8).
_EXCHANGE_ORDER = ("bybit", "okx", "binance", "gate", "bitget", "mexc", "htx", "bingx")
_EXCHANGE_LABELS = {
    "bybit":   "Bybit",
    "okx":     "OKX",
    "binance": "Binance",
    "gate":    "Gate.io",
    "bitget":  "Bitget",
    "mexc":    "MEXC",
    "htx":     "HTX",
    "bingx":   "BingX",
}


def _exchanges_keyboard(state: dict[str, Any]) -> dict[str, Any]:
    """Инлайн-клавиатура управления биржами (toggle).

    Зелёный кружок = включена (участвует в скане/торговле).
    Красный кружок = отключена вручную.
    Кнопка «← Назад» возвращает главное меню.
    """
    disabled: set[str] = set(_g(state).get("disabled_exchanges") or [])
    rows: list[list[dict[str, Any]]] = []

    # Биржи попарно в каждую строку.
    exchanges = [ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS]
    for i in range(0, len(exchanges), 2):
        row = []
        for ex in exchanges[i:i + 2]:
            icon = "🔴" if ex in disabled else "🟢"
            label = f"{icon} {_EXCHANGE_LABELS.get(ex, ex.upper())}"
            row.append({"text": label, "callback_data": CB_EX_TOGGLE_PREFIX + ex})
        rows.append(row)

    rows.append([{"text": "← Назад", "callback_data": CB_START + "_menu"}])
    return {"inline_keyboard": rows}


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
    return "✅ Арб-сканер <b>запущен</b>. Бот продолжает искать и вести арб-пары."


async def _handle_stop(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = False
    return "⏸ Арб-сканер <b>остановлен</b>. Активная позиция продолжает вестись до закрытия вручную."


async def _handle_stats(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    g = _g(state)
    arb_stats = arb_storage.get_total_stats()
    active_list = arb_storage.get_all_active()
    recent = arb_storage.get_recent_closed(limit=3)
    status = "▶️ активен" if g.get("bot_running", True) else "⏸ на паузе"
    ks = str(g.get("kill_switch_state") or "NONE")
    equity_start = g.get("equity_start")
    cum_pnl = float(g.get("cumulative_pnl", 0.0) or 0.0)
    equity_now = (float(equity_start) + cum_pnl) if equity_start is not None else None
    equity_line = f"{equity_now:.2f} USDT" if equity_now is not None else "-"

    lines = [
        "📊 <b>Статистика арбитража</b>",
        f"Статус: {status}  |  Kill-switch: {ks}",
        f"Эквити: {equity_line}",
        "",
        "<b>Закрытых арб-сделок:</b> " + str(arb_stats.get("n", 0)),
        f"  └ Total PnL: {arb_stats.get('pnl_sum', 0.0):+.4f} USDT",
        f"  └ Funding:   {arb_stats.get('funding_sum', 0.0):+.4f} USDT",
        f"  └ Direct.:   {arb_stats.get('dir_sum', 0.0):+.4f} USDT",
        f"  └ Fees est:  −{arb_stats.get('fees_sum', 0.0):.4f} USDT",
    ]
    if active_list:
        from datetime import datetime, timezone
        for active in active_list:
            held_h = ""
            try:
                opened_dt = datetime.fromisoformat(str(active["opened_ts"]))
                if opened_dt.tzinfo is None:
                    opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                held_h = f" ({(datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600:.1f}ч)"
            except Exception:  # noqa: BLE001
                pass
            lines += [
                "",
                f"<b>Пара #{active['id']}:</b> {active['symbol']}{held_h}",
                f"  LONG @ {active['long_exchange']} / SHORT @ {active['short_exchange']}",
                f"  Funding получено: {float(active.get('funding_received') or 0):+.4f} USDT",
            ]
    if recent:
        lines.append("")
        lines.append("<b>Последние закрытия:</b>")
        for r in recent:
            arrow = "▲" if (r.get("pnl_total") or 0) >= 0 else "▼"
            pnl = float(r.get("pnl_total") or 0.0)
            ts = (r.get("closed_ts") or "")[:16].replace("T", " ")
            lines.append(f"  #{r['id']} {r.get('symbol')} {arrow} {pnl:+.4f} ({ts})")
    return "\n".join(lines)


async def _handle_positions(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    from datetime import datetime, timezone
    from exchanges import get_adapter

    all_positions = arb_storage.get_all_active()
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    lines = [f"📂 <b>Арб-позиции</b>  [{len(all_positions)}/{max_pos}]"]

    if not all_positions:
        lines.append("Нет активных арб-пар.")
        return "\n".join(lines)

    for idx, active in enumerate(all_positions, start=1):
        sym = active.get("symbol", "-")
        long_ex  = active.get("long_exchange", "-")
        short_ex = active.get("short_exchange", "-")
        qty      = active.get("qty_base", "-")
        notional = active.get("notional_usdt", "-")
        long_entry  = float(active.get("long_entry") or 0)
        short_entry = float(active.get("short_entry") or 0)
        funding_rcv = float(active.get("funding_received") or 0)
        edge_apr    = float(active.get("edge_apr_open") or 0)
        opened      = str(active.get("opened_ts") or "-")[:19].replace("T", " ")

        held_h = ""
        try:
            opened_dt = datetime.fromisoformat(str(active["opened_ts"]))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            held_h = f"  ⏱ {(datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600:.1f}ч"
        except Exception:  # noqa: BLE001
            pass

        lines += [
            "",
            f"<b>── Пара #{active.get('id')}  ({idx}/{len(all_positions)}) ──</b>",
            f"Символ: <b>{sym}</b>  Открыта: {opened}{held_h}",
            f"🟢 LONG  @ <b>{long_ex}</b>  вход: {long_entry:.4f}  qty: {qty}",
            f"🔴 SHORT @ <b>{short_ex}</b>  вход: {short_entry:.4f}  qty: {qty}",
            f"Notional: ~{notional} USDT  |  Funding: <b>{funding_rcv:+.4f}</b>  |  APR вх.: {edge_apr*100:.2f}%",
        ]

        for ex_name in (long_ex, short_ex):
            try:
                adapter = get_adapter(ex_name)
                ex_pos_list = await adapter.get_positions(session, sym)
                for p in (ex_pos_list or []):
                    upnl = p.get("unrealisedPnl") or p.get("unRealisedPnl")
                    side = p.get("side")
                    if upnl is not None:
                        lines.append(f"  {ex_name} uPnL ({side}): {float(upnl):+.4f} USDT")
            except Exception:  # noqa: BLE001
                pass

    return "\n".join(lines)


async def _handle_panic(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Первый шаг: показать диалог подтверждения, ноги НЕ трогаем."""
    positions = arb_storage.get_all_active()
    if not positions:
        return (
            "🚨 Активных арб-пар нет — нечего закрывать.",
            set_keyboard(),
        )
    pair_lines = "\n".join(
        f"  #{p['id']} {p.get('symbol', '-')} — "
        f"LONG@{p.get('long_exchange', '-')} SHORT@{p.get('short_exchange', '-')}"
        for p in positions
    )
    count = len(positions)
    text = (
        f"🚨 <b>ЗАКРЫТЬ АРБ — подтверждение</b>\n\n"
        f"Будет принудительно закрыто <b>{count}</b> пар:\n"
        f"{pair_lines}\n\n"
        "Все ноги будут закрыты маркетом. Продолжить?"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚠️ ДА, ЗАКРЫТЬ ВСЕ", "callback_data": CB_PANIC_CONFIRM},
                {"text": "Отмена",               "callback_data": CB_PANIC_CANCEL},
            ]
        ]
    }
    return text, keyboard


async def _handle_panic_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Второй шаг: принудительно закрываем ВСЕ арб-пары через executor."""
    _g(state)["bot_running"] = False
    positions = arb_storage.get_all_active()
    if not positions:
        return "🚨 Активных арб-пар уже нет."
    if getattr(config, "DRY_RUN", False):
        return "[DRY RUN] 🚨 Принудительное закрытие имитировано. Реальные ордера не отправлены."
    results: list[str] = []
    for pos in positions:
        try:
            await arb_executor._force_close(
                session, _FUNDING_ADAPTERS, pos, "manual_panic", None
            )
            results.append(f"#{pos['id']} {pos.get('symbol', '-')} — закрыта ✓")
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] Ошибка _force_close #{pos.get('id')}: {exc}")
            results.append(f"#{pos['id']} {pos.get('symbol', '-')} — ошибка: {exc}")
    summary = "\n".join(results)
    return (
        f"🚨 Принудительное закрытие завершено:\n{summary}\n\n"
        "Арб-сканер остановлен. Нажмите ▶️ СТАРТ для возобновления."
    )


async def _handle_panic_cancel(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return "Отменено. Арб-позиция не тронута."


async def _handle_arb_status(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """⚡ АРБ СТАТУС — детальный отчёт executor'а (активная пара + закрытые)."""
    return arb_executor.format_status()


async def _handle_keys(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """🔑 КЛЮЧИ — маскированный статус API-ключей + инструкция по смене."""
    return key_manager.get_status_report()


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


async def _handle_exchanges(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """🏦 БИРЖИ — показать статус бирж с кнопками включить/отключить."""
    g = _g(state)
    disabled: set[str] = set(g.get("disabled_exchanges") or [])
    enabled_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS and ex not in disabled])
    total_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS])
    text = (
        "🏦 <b>Управление биржами</b>\n\n"
        f"Активных: <b>{enabled_count}/{total_count}</b>\n"
        "Нажмите на биржу, чтобы включить или отключить её.\n"
        "🟢 = включена  |  🔴 = отключена\n\n"
        "⚠️ Отключение биржи останавливает поиск новых пар через неё.\n"
        "Уже открытые позиции мониторятся до закрытия."
    )
    return text, _exchanges_keyboard(state)


async def _handle_exchange_toggle(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    exchange_name: str,
) -> tuple[str, dict[str, Any]]:
    """Toggle включён/отключён для конкретной биржи."""
    g = _g(state)
    disabled: set[str] = set(g.get("disabled_exchanges") or [])
    label = _EXCHANGE_LABELS.get(exchange_name, exchange_name.upper())

    if exchange_name in disabled:
        disabled.discard(exchange_name)
        action = f"✅ <b>{label}</b> включена в скан и торговлю."
    else:
        # Проверка: нельзя отключить биржу с активной арб-позицией
        for active_pos in arb_storage.get_all_active():
            long_ex = str(active_pos.get("long_exchange") or "").lower()
            short_ex = str(active_pos.get("short_exchange") or "").lower()
            if exchange_name in (long_ex, short_ex):
                text = (
                    f"⚠️ Нельзя отключить <b>{label}</b>: на этой бирже "
                    f"открыта активная арб-позиция #{active_pos.get('id')}.\n"
                    "Сначала закройте позицию."
                )
                return text, _exchanges_keyboard(state)
        disabled.add(exchange_name)
        action = f"🔴 <b>{label}</b> отключена. Новые пары через неё открываться не будут."

    g["disabled_exchanges"] = list(disabled)

    enabled_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS and ex not in disabled])
    total_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS])
    text = (
        f"{action}\n\n"
        f"Активных бирж: <b>{enabled_count}/{total_count}</b>"
    )
    return text, _exchanges_keyboard(state)


async def _handle_funding(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """📡 ФАНДИНГ — текущий funding-скан по всем биржам.

    Сначала пробуем кэш из state (обновляется каждые FUNDING_SCAN_INTERVAL_SEC),
    если кэша нет — делаем ad-hoc скан прямо сейчас.
    """
    g = _g(state)
    snapshots = g.get("funding_snapshot")

    if not snapshots:
        if not _FUNDING_ADAPTERS:
            return (
                "📡 Сканер не настроен. Задайте FUNDING_SCAN_EXCHANGES в config "
                "и убедитесь, что адаптеры зарегистрированы."
            )
        try:
            snapshots = await arbitrage_engine.scan_funding(session, _FUNDING_ADAPTERS)
            g["funding_snapshot"] = snapshots
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] /funding: ошибка scan_funding: {exc}")
            return "📡 Не удалось снять funding по биржам. Сетевая ошибка."

    if not any(snapshots.values()):
        return "📡 Funding-данных нет (все адаптеры вернули пусто)."

    return arbitrage_engine.format_full_report(snapshots)


_HANDLERS = {
    CB_START:              _handle_start,
    CB_STOP:               _handle_stop,
    CB_STATS:              _handle_stats,
    CB_POSITIONS:          _handle_positions,
    CB_ARB_STATUS:         _handle_arb_status,
    CB_FUNDING:            _handle_funding,
    CB_PANIC:              _handle_panic,
    CB_PANIC_CONFIRM:      _handle_panic_confirm,
    CB_PANIC_CANCEL:       _handle_panic_cancel,
    CB_KILL:               _handle_kill_state,
    CB_RESUME_MDD:         _handle_resume_mdd,
    CB_RESUME_MDD_CONFIRM: _handle_resume_mdd_confirm,
    CB_RESUME_MDD_CANCEL:  _handle_resume_mdd_cancel,
    CB_KEYS:               _handle_keys,
    CB_EXCHANGES:          _handle_exchanges,
    # "← Назад" в меню бирж возвращает главное меню.
    CB_START + "_menu":    _handle_start,
}


async def _process_callback(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    cb: dict[str, Any],
) -> None:
    cb_id = cb.get("id")
    data = cb.get("data", "")

    # Обработка toggle-кнопок бирж (префикс "zc:ext:").
    if data.startswith(CB_EX_TOGGLE_PREFIX):
        ex_name = data[len(CB_EX_TOGGLE_PREFIX):]
        if cb_id:
            await answer_callback(session, cb_id, "Готово")
        try:
            text, keyboard = await _handle_exchange_toggle(session, state, ex_name)
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] Ошибка exchange_toggle {ex_name}: {exc}")
            text, keyboard = f"Ошибка: {exc}", set_keyboard()
        await send_message(session, text, reply_markup=keyboard)
        return

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
                "👋 <b>Zenith-Control Ultimate v2 — Funding Arbitrage</b>\n"
                "8 бирж: Bybit · OKX · Binance · Gate · Bitget · MEXC · HTX · BingX\n"
                "Используйте кнопки ниже.\n\n"
                "<b>Кнопки:</b>\n"
                "▶️ СТАРТ / ⏸ СТОП — пауза арб-сканера\n"
                "📊 СТАТИСТИКА — сводка по арб-сделкам\n"
                "📂 ПОЗИЦИИ — детали активной арб-пары\n"
                "⚡ АРБ СТАТУС — отчёт executor'а\n"
                "📡 ФАНДИНГ — текущий funding-скан по биржам\n"
                "🚨 ЗАКРЫТЬ АРБ — принудительное закрытие пары\n"
                "🛡 KILL-STATE — статус kill-switch / просадки\n"
                "✅ СНЯТЬ MDD — снять MDD kill-switch вручную\n"
                "🔑 КЛЮЧИ — статус и быстрая смена API-ключей\n"
                "🏦 БИРЖИ — включить/отключить биржи вручную\n\n"
                "<b>Текстовые команды:</b>\n"
                "<code>/status</code> — краткая статистика\n"
                "<code>/arb_status</code> — статус executor'а\n"
                "<code>/funding</code> — funding-скан\n"
                "<code>/exchanges</code> — управление биржами\n"
                "<code>/resume_kill_switch</code> — снять MDD\n"
                "<code>/setkey ИМЯ значение</code> — сменить API-ключ\n"
                "<code>/delkey ИМЯ</code> — сбросить к Replit-секрету"
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
        if isinstance(result, tuple) and len(result) == 2:
            reply, keyboard = result
        else:
            reply = result
            keyboard = set_keyboard()
        await send_message(session, reply, reply_markup=keyboard)
        return
    if lowered in ("/arb", "/funding"):
        report = await _handle_funding(session, state)
        await send_message(session, report)
        await send_message(session, "Меню ниже.", reply_markup=set_keyboard())
        return
    if lowered == "/exchanges":
        text, keyboard = await _handle_exchanges(session, state)
        await send_message(session, text, reply_markup=keyboard)
        return
    if lowered == "/arb_status":
        await send_message(
            session,
            arb_executor.format_status(),
            reply_markup=set_keyboard(),
        )
        return
    # /setkey ИМЯ значение — сменить API-ключ в рантайме
    if lowered.startswith("/setkey "):
        parts = text.split(None, 2)  # ["/setkey", "ИМЯ", "значение"]
        if len(parts) < 3:
            await send_message(
                session,
                "Формат: <code>/setkey ИМЯ значение</code>\n"
                "Пример: <code>/setkey OKX_API_KEY abc123xyz</code>",
                reply_markup=set_keyboard(),
            )
            return
        key_name, key_value = parts[1].upper(), parts[2]
        try:
            key_manager.set_key(key_name, key_value)
            await send_message(
                session,
                f"✅ <b>{key_name}</b> обновлён и применён немедленно.\n\n"
                "⚠️ <b>Удалите это сообщение из чата!</b>",
                reply_markup=set_keyboard(),
            )
        except ValueError as exc:
            await send_message(
                session, f"❌ Ошибка: {exc}", reply_markup=set_keyboard()
            )
        return

    # /delkey ИМЯ — сбросить оверрайд, Replit-секрет снова станет активным
    if lowered.startswith("/delkey "):
        parts = text.split(None, 1)
        if len(parts) < 2:
            await send_message(
                session,
                "Формат: <code>/delkey ИМЯ</code>\n"
                "Пример: <code>/delkey OKX_API_KEY</code>",
                reply_markup=set_keyboard(),
            )
            return
        key_name = parts[1].strip().upper()
        if key_manager.delete_key(key_name):
            await send_message(
                session,
                f"✅ Оверрайд <b>{key_name}</b> удалён. "
                "Теперь используется Replit-секрет (если задан).",
                reply_markup=set_keyboard(),
            )
        else:
            await send_message(
                session,
                f"ℹ️ Оверрайда для <b>{key_name}</b> не было — ничего не изменилось.",
                reply_markup=set_keyboard(),
            )
        return

    # Любое другое сообщение — показываем меню.
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
