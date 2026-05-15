"""Telegram-терминал Zenith Funding Arbitrage Bot v3.

Long polling через aiohttp. Авторизация по chat_id.
Все тексты — на русском. HTML-парсинг.
"""

from __future__ import annotations

import asyncio
import json
import time
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


# ─── Константы ────────────────────────────────────────────────────────

EXCHANGE = get_adapter(config.EXCHANGE)

_FUNDING_ADAPTERS: dict[str, Any] = {}
for _ex_name in getattr(config, "FUNDING_SCAN_EXCHANGES", ()):
    try:
        _FUNDING_ADAPTERS[_ex_name] = get_adapter(_ex_name)
    except Exception as _exc:  # noqa: BLE001
        print(f"[TG] Funding-adapter {_ex_name} unavailable: {_exc}")

_DIVIDER = "\u2501" * 24


# ─── Callback data ────────────────────────────────────────────────────

CB_START = "zc:start"
CB_STOP = "zc:stop"
CB_STATS = "zc:stats"
CB_POSITIONS = "zc:positions"
CB_ARB_STATUS = "zc:arb"
CB_FUNDING = "zc:fund"
CB_PANIC = "zc:panic"
CB_KILL = "zc:kill"
CB_RESUME_MDD = "zc:resume_mdd"
CB_KEYS = "zc:keys"
CB_EXCHANGES = "zc:exchanges"
CB_SYMBOLS = "zc:sym"
CB_AI = "zc:ai"

CB_PANIC_CONFIRM = "zc:panic_ok"
CB_PANIC_CANCEL = "zc:panic_no"
CB_RESUME_MDD_CONFIRM = "zc:mdd_ok"
CB_RESUME_MDD_CANCEL = "zc:mdd_no"

CB_EX_TOGGLE_PREFIX = "zc:ext:"
CB_SYM_TOGGLE_PREFIX = "zc:sy:"


# ─── Helper: _card ────────────────────────────────────────────────────

def _card(title: str, emoji: str, body_lines: list[str], footer: str = "") -> str:
    """Универсальная моноширинная карточка."""
    header = f"{emoji} <b>{title}</b>"
    body = "\n".join(body_lines)
    parts = [header, _DIVIDER, f"<pre>{body}</pre>"]
    if footer:
        parts.append(f"<i>{footer}</i>")
    return "\n".join(parts)


# ─── Telegram API helpers ─────────────────────────────────────────────

def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


def _g(state: dict[str, Any]) -> dict[str, Any]:
    """Вернуть global-секцию state (с fallback для v1)."""
    g = state.get("global") if isinstance(state, dict) else None
    if isinstance(g, dict):
        return g
    return state




# ─── Клавиатура ───────────────────────────────────────────────────────

def set_keyboard() -> dict[str, Any]:
    """Главная инлайн-клавиатура (6 строк)."""
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4ca Статус", "callback_data": CB_STATS},
                {"text": "\U0001f4e1 Фандинг", "callback_data": CB_FUNDING},
            ],
            [
                {"text": "\U0001f4b0 Пары", "callback_data": CB_POSITIONS},
                {"text": "\u2696\ufe0f Балансы", "callback_data": CB_ARB_STATUS},
            ],
            [
                {"text": "\U0001f4b1 Символы", "callback_data": CB_SYMBOLS},
                {"text": "\U0001f3e6 Биржи", "callback_data": CB_EXCHANGES},
            ],
            [
                {"text": "\U0001f916 AI", "callback_data": CB_AI},
                {"text": "\U0001f511 Ключи", "callback_data": CB_KEYS},
            ],
            [
                {"text": "\U0001f6a8 PANIC", "callback_data": CB_PANIC},
                {"text": "\U0001f6e1 Kill", "callback_data": CB_KILL},
            ],
            [
                {"text": "\u25b6\ufe0f Старт", "callback_data": CB_START},
                {"text": "\u23f8 Пауза", "callback_data": CB_STOP},
            ],
        ]
    }


_EXCHANGE_ORDER = ("bybit", "okx", "binance", "gate", "bitget", "mexc", "htx", "bingx")
_EXCHANGE_LABELS = {
    "bybit": "Bybit",
    "okx": "OKX",
    "binance": "Binance",
    "gate": "Gate.io",
    "bitget": "Bitget",
    "mexc": "MEXC",
    "htx": "HTX",
    "bingx": "BingX",
}


def _exchanges_keyboard(state: dict[str, Any]) -> dict[str, Any]:
    """Инлайн-клавиатура toggle бирж."""
    disabled: set[str] = set(_g(state).get("disabled_exchanges") or [])
    rows: list[list[dict[str, Any]]] = []
    exchanges = [ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS]
    for i in range(0, len(exchanges), 2):
        row = []
        for ex in exchanges[i:i + 2]:
            icon = "\U0001f534" if ex in disabled else "\U0001f7e2"
            label = f"{icon} {_EXCHANGE_LABELS.get(ex, ex.upper())}"
            row.append({"text": label, "callback_data": CB_EX_TOGGLE_PREFIX + ex})
        rows.append(row)
    rows.append([{"text": "\u2190 \u041d\u0430\u0437\u0430\u0434", "callback_data": CB_START + "_menu"}])
    return {"inline_keyboard": rows}


def _symbols_keyboard(state: dict[str, Any]) -> dict[str, Any]:
    """Инлайн-клавиатура toggle символов."""
    g = _g(state)
    override: set[str] = set(g.get("allowed_symbols_override") or [])
    all_symbols = list(getattr(config, "FUNDING_SCAN_SYMBOLS", []))
    rows: list[list[dict[str, Any]]] = []
    for i in range(0, len(all_symbols), 2):
        row = []
        for sym in all_symbols[i:i + 2]:
            if not override:
                icon = "\U0001f7e2"
            else:
                icon = "\U0001f7e2" if sym in override else "\u26aa"
            row.append({"text": f"{icon} {sym.replace('USDT', '')}", "callback_data": CB_SYM_TOGGLE_PREFIX + sym})
        rows.append(row)
    rows.append([{"text": "\u2190 \u041d\u0430\u0437\u0430\u0434", "callback_data": CB_START + "_menu"}])
    return {"inline_keyboard": rows}




# ─── Telegram send / answer ───────────────────────────────────────────

async def send_message(
    session: aiohttp.ClientSession,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
    chat_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram."""
    if not config.TELEGRAM_TOKEN:
        print("[TG] TELEGRAM_TOKEN not set, skip send")
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
                print(f"[TG] sendMessage status {resp.status}: {body[:200]}")
                return None
            return await resp.json()
    except aiohttp.ClientError as exc:
        print(f"[TG] network error sendMessage: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] unexpected error sendMessage: {exc}")
        return None


async def _delete_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    message_id: int,
) -> None:
    """Удалить сообщение (молча проглатываем ошибки)."""
    if not config.TELEGRAM_TOKEN:
        return
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        async with session.post(_bot_url("deleteMessage"), data=payload, timeout=10) as resp:
            if resp.status != 200:
                pass  # У бота может не быть прав
    except Exception:  # noqa: BLE001
        pass


async def answer_callback(
    session: aiohttp.ClientSession,
    callback_id: str,
    text: str = "",
    show_alert: bool = False,
) -> None:
    """answerCallbackQuery."""
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
                print(f"[TG] answerCallbackQuery status {resp.status}: {body[:200]}")
    except aiohttp.ClientError as exc:
        print(f"[TG] network error answerCallbackQuery: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[TG] unexpected error answerCallbackQuery: {exc}")




# ─── Auth / time helpers ──────────────────────────────────────────────

def _is_authorized(update: dict[str, Any]) -> bool:
    """True только для единственного разрешённого chat_id."""
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
        print(f"[TG] auth check error: {exc}")
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




# ─── Обработчики кнопок ───────────────────────────────────────────────

async def _handle_start(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = True
    return _card("Сканер запущен", "\u2705", [
        "Арбитраж-сканер активен.",
        "Бот ищет и ведёт funding-связки.",
    ])


async def _handle_stop(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    _g(state)["bot_running"] = False
    return _card("Сканер на паузе", "\u23f8", [
        "Новые связки НЕ открываются.",
        "Активные позиции мониторятся до закрытия.",
    ])


async def _handle_stats(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    g = _g(state)
    arb_stats = arb_storage.get_total_stats()
    active_list = arb_storage.get_all_active()
    recent = arb_storage.get_recent_closed(limit=3)
    status = "\u25b6\ufe0f активен" if g.get("bot_running", True) else "\u23f8 пауза"
    ks = str(g.get("kill_switch_state") or "NONE")
    cum_pnl = float(g.get("cumulative_pnl", 0.0) or 0.0)
    equity_start = g.get("equity_start")
    equity_now = (float(equity_start) + cum_pnl) if equity_start is not None else None
    equity_line = f"{equity_now:.2f} USDT" if equity_now is not None else "-"

    body = [
        f"Статус: {status}  |  Kill: {ks}",
        f"Эквити: {equity_line}",
        "",
        f"Закрытых сделок: {arb_stats.get('n', 0)}",
        f"  PnL итого:  {arb_stats.get('pnl_sum', 0.0):+.4f} USDT",
        f"  Funding:    {arb_stats.get('funding_sum', 0.0):+.4f} USDT",
        f"  Direction:  {arb_stats.get('dir_sum', 0.0):+.4f} USDT",
        f"  Комиссии:  -{arb_stats.get('fees_sum', 0.0):.4f} USDT",
    ]

    if active_list:
        for active in active_list:
            held_h = ""
            try:
                opened_dt = datetime.fromisoformat(str(active["opened_ts"]))
                if opened_dt.tzinfo is None:
                    opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                held_h = f" ({(datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600:.1f}\u0447)"
            except Exception:  # noqa: BLE001
                pass
            body += [
                "",
                f"#{active['id']} {active['symbol']}{held_h}",
                f"  LONG@{active['long_exchange']} / SHORT@{active['short_exchange']}",
                f"  Funding: {float(active.get('funding_received') or 0):+.4f}",
            ]

    if recent:
        body.append("")
        body.append("--- Последние закрытия ---")
        for r in recent:
            arrow = "\u25b2" if (r.get("pnl_total") or 0) >= 0 else "\u25bc"
            pnl = float(r.get("pnl_total") or 0.0)
            ts = (r.get("closed_ts") or "")[:16].replace("T", " ")
            body.append(f"  #{r['id']} {r.get('symbol')} {arrow} {pnl:+.4f} ({ts})")

    return _card("Статистика", "\U0001f4ca", body)


async def _handle_positions(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    all_positions = arb_storage.get_all_active()
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))

    if not all_positions:
        return _card("Арб-позиции", "\U0001f4b0", [
            f"Слотов: 0/{max_pos}",
            "Активных связок нет.",
        ])

    body: list[str] = [f"Слотов: {len(all_positions)}/{max_pos}"]

    for idx, active in enumerate(all_positions, start=1):
        sym = active.get("symbol", "-")
        long_ex = active.get("long_exchange", "-")
        short_ex = active.get("short_exchange", "-")
        qty = active.get("qty_base", "-")
        notional = active.get("notional_usdt", "-")
        long_entry = float(active.get("long_entry") or 0)
        short_entry = float(active.get("short_entry") or 0)
        funding_rcv = float(active.get("funding_received") or 0)
        edge_apr = float(active.get("edge_apr_open") or 0)

        held_h = ""
        try:
            opened_dt = datetime.fromisoformat(str(active["opened_ts"]))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
            held_h = f" {(datetime.now(tz=timezone.utc) - opened_dt).total_seconds() / 3600:.1f}\u0447"
        except Exception:  # noqa: BLE001
            pass

        body += [
            "",
            f"== #{active.get('id')} {sym} ({idx}/{len(all_positions)}){held_h} ==",
            f"  LONG  @ {long_ex}  |\u0446\u0435\u043d\u0430: {long_entry:.4f}",
            f"  SHORT @ {short_ex} |\u0446\u0435\u043d\u0430: {short_entry:.4f}",
            f"  Qty: {qty} | Notional: ~{notional} USDT",
            f"  Funding: {funding_rcv:+.4f} | APR\u0432\u0445: {edge_apr*100:.2f}%",
        ]

    return _card("\u0410\u0440\u0431-\u043f\u043e\u0437\u0438\u0446\u0438\u0438", "\U0001f4b0", body)


async def _handle_arb_status(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return arb_executor.format_status()


async def _handle_keys(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
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
        print(f"[TG] get_current_drawdown error: {exc}")
        current_dd = 0.0
    equity_start = g.get("equity_start")
    equity_line = f"{float(equity_start):.4f}" if equity_start is not None else "не задан"
    bot_running = "включен" if g.get("bot_running", True) else "пауза"
    detail = str(g.get("kill_detail") or "")

    body = [
        f"Kill-switch: {ks}",
        f"До снятия:   {remaining}",
        f"Дедлайн:     {until_iso or '-'}",
        f"Суточный PnL:  {daily_pnl:.4f}",
        f"Недельный PnL: {weekly_pnl:.4f}",
        f"Просадка:      {current_dd * 100:.2f}%",
        f"Эквити старт:  {equity_line}",
        f"Торговля:      {bot_running}",
    ]
    if detail:
        body.append(f"Причина: {detail}")
    return _card("Kill-State", "\U0001f6e1", body)


async def _handle_panic(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Первый шаг: диалог подтверждения."""
    positions = arb_storage.get_all_active()
    if not positions:
        return (
            _card("PANIC", "\U0001f6a8", ["Активных связок нет — закрывать нечего."]),
            set_keyboard(),
        )
    pair_lines = [
        f"  #{p['id']} {p.get('symbol', '-')} "
        f"LONG@{p.get('long_exchange', '-')} SHORT@{p.get('short_exchange', '-')}"
        for p in positions
    ]
    body = [
        f"Будет закрыто связок: {len(positions)}",
        "",
    ] + pair_lines + [
        "",
        "Все ноги закрываются маркетом.",
        "Подтвердите действие.",
    ]
    text = _card("Принудительное закрытие", "\U0001f6a8", body)
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "\u26a0\ufe0f ДА, ЗАКРЫТЬ ВСЕ", "callback_data": CB_PANIC_CONFIRM},
                {"text": "Отмена", "callback_data": CB_PANIC_CANCEL},
            ]
        ]
    }
    return text, keyboard


async def _handle_panic_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Второй шаг: закрываем ВСЕ пары."""
    _g(state)["bot_running"] = False
    positions = arb_storage.get_all_active()
    if not positions:
        return _card("PANIC", "\U0001f6a8", ["Активных связок уже нет."])
    if getattr(config, "DRY_RUN", False):
        return "[DRY RUN] Принудительное закрытие имитировано."
    results: list[str] = []
    for pos in positions:
        try:
            await arb_executor._force_close(
                session, _FUNDING_ADAPTERS, pos, "manual_panic", None
            )
            results.append(f"#{pos['id']} {pos.get('symbol', '-')} \u2014 \u0437\u0430\u043a\u0440\u044b\u0442\u0430")
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] _force_close #{pos.get('id')} error: {exc}")
            results.append(f"#{pos['id']} {pos.get('symbol', '-')} \u2014 \u043e\u0448\u0438\u0431\u043a\u0430: {exc}")
    body = results + ["", "Сканер остановлен. Нажмите Старт для возобновления."]
    return _card("Закрытие завершено", "\U0001f6a8", body)


async def _handle_panic_cancel(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return _card("Отменено", "\u2705", ["Позиции не тронуты."])




async def _handle_resume_mdd(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Снять MDD kill-switch — запрос подтверждения."""
    g = _g(state)
    if g.get("kill_switch_state") != "MDD":
        return (
            _card("MDD", "\u2705", ["MDD не активен, сбрасывать нечего."]),
            set_keyboard(),
        )
    text = _card("Снять MDD kill-switch", "\u2705", [
        f"MDD срабатывает при просадке >= {config.MAX_DRAWDOWN * 100:.0f}% от HWM.",
        "Снимается ТОЛЬКО вручную.",
        "Убедитесь, что понимаете текущую просадку.",
        "",
        "Снять блокировку?",
    ])
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "\u2705 ДА, СНЯТЬ", "callback_data": CB_RESUME_MDD_CONFIRM},
                {"text": "Отмена", "callback_data": CB_RESUME_MDD_CANCEL},
            ]
        ]
    }
    return text, keyboard


async def _handle_resume_mdd_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    g = _g(state)
    if g.get("kill_switch_state") != "MDD":
        return _card("MDD", "\u2705", ["MDD уже не активен."])
    g["kill_switch_state"] = "NONE"
    g["kill_until_utc"] = None
    g["kill_detail"] = ""
    return _card("MDD снят", "\u2705", ["Kill-switch снят вручную.", "Торговля возобновится при включённом сканере."])


async def _handle_resume_mdd_cancel(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return _card("Отменено", "\u2139", ["MDD kill-switch остаётся активным."])


async def _handle_exchanges(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Управление биржами."""
    g = _g(state)
    disabled: set[str] = set(g.get("disabled_exchanges") or [])
    enabled_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS and ex not in disabled])
    total_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS])
    body = [
        f"Активных: {enabled_count}/{total_count}",
        "",
        "Нажмите на биржу чтобы вкл/выкл.",
        "\U0001f7e2 = включена  |  \U0001f534 = отключена",
        "",
        "Отключение останавливает поиск новых связок.",
        "Открытые позиции мониторятся до закрытия.",
    ]
    text = _card("Управление биржами", "\U0001f3e6", body)
    return text, _exchanges_keyboard(state)


async def _handle_exchange_toggle(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    exchange_name: str,
) -> tuple[str, dict[str, Any]]:
    """Toggle биржи."""
    g = _g(state)
    disabled: set[str] = set(g.get("disabled_exchanges") or [])
    label = _EXCHANGE_LABELS.get(exchange_name, exchange_name.upper())

    if exchange_name in disabled:
        disabled.discard(exchange_name)
        action = f"\U0001f7e2 <b>{label}</b> включена."
    else:
        for active_pos in arb_storage.get_all_active():
            long_ex = str(active_pos.get("long_exchange") or "").lower()
            short_ex = str(active_pos.get("short_exchange") or "").lower()
            if exchange_name in (long_ex, short_ex):
                text = _card("Ошибка", "\u26a0\ufe0f", [
                    f"Нельзя отключить {label}:",
                    f"открыта позиция #{active_pos.get('id')}.",
                    "Сначала закройте позицию.",
                ])
                return text, _exchanges_keyboard(state)
        disabled.add(exchange_name)
        action = f"\U0001f534 <b>{label}</b> отключена."

    g["disabled_exchanges"] = list(disabled)
    enabled_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS and ex not in disabled])
    total_count = len([ex for ex in _EXCHANGE_ORDER if ex in _FUNDING_ADAPTERS])
    text = f"{action}\nАктивных бирж: <b>{enabled_count}/{total_count}</b>"
    return text, _exchanges_keyboard(state)




async def _handle_symbols(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Toggle символов для арб-скана."""
    g = _g(state)
    override: set[str] = set(g.get("allowed_symbols_override") or [])
    all_symbols = list(getattr(config, "FUNDING_SCAN_SYMBOLS", []))
    active_count = len(override) if override else len(all_symbols)
    body = [
        f"Разрешённых символов: {active_count}/{len(all_symbols)}",
        "",
        "Нажмите символ чтобы вкл/выкл.",
        "\U0001f7e2 = включен  |  \u26aa = выключен",
        "",
        "Пустой override = все символы разрешены.",
    ]
    text = _card("Символы для скана", "\U0001f4b1", body)
    return text, _symbols_keyboard(state)


async def _handle_symbol_toggle(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    symbol: str,
) -> tuple[str, dict[str, Any]]:
    """Toggle символа."""
    g = _g(state)
    override: set[str] = set(g.get("allowed_symbols_override") or [])
    all_symbols = list(getattr(config, "FUNDING_SCAN_SYMBOLS", []))

    if not override:
        # Первое нажатие: включаем все кроме этого
        override = set(all_symbols) - {symbol}
    else:
        if symbol in override:
            override.discard(symbol)
        else:
            override.add(symbol)
        # Если все включены — сбрасываем override
        if override == set(all_symbols):
            override = set()

    g["allowed_symbols_override"] = list(override) if override else []
    active_count = len(override) if override else len(all_symbols)
    short_sym = symbol.replace("USDT", "")
    if override and symbol in override:
        action = f"\U0001f7e2 {short_sym} включен"
    elif override and symbol not in override:
        action = f"\u26aa {short_sym} выключен"
    else:
        action = "Все символы разрешены"
    text = f"{action}\nАктивных: <b>{active_count}/{len(all_symbols)}</b>"
    return text, _symbols_keyboard(state)


async def _handle_ai(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """AI-статус: announcement monitor, ML curator, anomaly detector."""
    g = _g(state)
    body: list[str] = []

    # Announcement monitor
    body.append("-- Announcement Monitor --")
    last_ann = float(g.get("last_announcement_check_epoch") or 0.0)
    if last_ann > 0:
        age_min = (time.time() - last_ann) / 60
        body.append(f"  Посл. скан: {age_min:.0f} мин назад")
    else:
        body.append("  Посл. скан: ещё не было")
    blacklist = g.get("announcement_blacklist") or {}
    body.append(f"  Blacklist: {len(blacklist)} символов")

    # ML Curator
    body.append("")
    body.append("-- ML Curator --")
    try:
        import ml_curator
        model = ml_curator.load_model("curator_model.json")
        if model:
            acc = model.get("accuracy", 0.0)
            body.append(f"  Модель: загружена (accuracy {acc*100:.1f}%)")
        else:
            body.append("  Модель: не загружена")
    except Exception:  # noqa: BLE001
        body.append("  Модель: недоступна")

    # Funding predictor
    body.append("")
    body.append("-- Funding Predictor --")
    try:
        import funding_predictor
        loaded = hasattr(funding_predictor, "_MODEL") and funding_predictor._MODEL is not None
        body.append(f"  Модель: {'загружена' if loaded else 'не загружена'}")
    except Exception:  # noqa: BLE001
        body.append("  Модель: недоступна")

    # Anomaly detector
    body.append("")
    body.append("-- Anomaly Detector --")
    try:
        import anomaly_detector
        detector = anomaly_detector.get_detector()
        n_trackers = len(detector._trackers)
        body.append(f"  Метрик: {n_trackers}")
        # Circuit breakers
        try:
            import circuit_breaker as cb_mod
            snap = cb_mod.get_breaker().status_snapshot()
            open_breakers = [k for k, v in snap.items() if v.get("state") == "OPEN"]
            if open_breakers:
                body.append(f"  Breakers OPEN: {', '.join(open_breakers)}")
            else:
                body.append("  Breakers: все закрыты")
        except Exception:  # noqa: BLE001
            body.append("  Breakers: н/д")
    except Exception:  # noqa: BLE001
        body.append("  Недоступен")

    return _card("AI / Мониторинг", "\U0001f916", body)


async def _handle_funding(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Funding-скан по всем биржам."""
    g = _g(state)
    snapshots = g.get("funding_snapshot")

    if not snapshots:
        if not _FUNDING_ADAPTERS:
            return _card("Фандинг", "\U0001f4e1", [
                "Сканер не настроен.",
                "Задайте FUNDING_SCAN_EXCHANGES в config.",
            ])
        try:
            snapshots = await arbitrage_engine.scan_funding(session, _FUNDING_ADAPTERS)
            g["funding_snapshot"] = snapshots
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] /funding: scan_funding error: {exc}")
            return _card("Фандинг", "\U0001f4e1", ["Ошибка при сканировании."])

    if not any(snapshots.values()):
        return _card("Фандинг", "\U0001f4e1", ["Данных нет (все адаптеры вернули пусто)."])

    return arbitrage_engine.format_full_report(snapshots)




# ─── Handler dispatch ─────────────────────────────────────────────────

_HANDLERS = {
    CB_START: _handle_start,
    CB_STOP: _handle_stop,
    CB_STATS: _handle_stats,
    CB_POSITIONS: _handle_positions,
    CB_ARB_STATUS: _handle_arb_status,
    CB_FUNDING: _handle_funding,
    CB_PANIC: _handle_panic,
    CB_PANIC_CONFIRM: _handle_panic_confirm,
    CB_PANIC_CANCEL: _handle_panic_cancel,
    CB_KILL: _handle_kill_state,
    CB_RESUME_MDD: _handle_resume_mdd,
    CB_RESUME_MDD_CONFIRM: _handle_resume_mdd_confirm,
    CB_RESUME_MDD_CANCEL: _handle_resume_mdd_cancel,
    CB_KEYS: _handle_keys,
    CB_EXCHANGES: _handle_exchanges,
    CB_SYMBOLS: _handle_symbols,
    CB_AI: _handle_ai,
    CB_START + "_menu": _handle_start,
}


async def _process_callback(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    cb: dict[str, Any],
) -> None:
    cb_id = cb.get("id")
    data = cb.get("data", "")

    # Toggle бирж
    if data.startswith(CB_EX_TOGGLE_PREFIX):
        ex_name = data[len(CB_EX_TOGGLE_PREFIX):]
        if cb_id:
            await answer_callback(session, cb_id, "Готово")
        try:
            text, keyboard = await _handle_exchange_toggle(session, state, ex_name)
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] exchange_toggle {ex_name} error: {exc}")
            text, keyboard = f"Ошибка: {exc}", set_keyboard()
        await send_message(session, text, reply_markup=keyboard)
        return

    # Toggle символов
    if data.startswith(CB_SYM_TOGGLE_PREFIX):
        sym = data[len(CB_SYM_TOGGLE_PREFIX):]
        if cb_id:
            await answer_callback(session, cb_id, "Готово")
        try:
            text, keyboard = await _handle_symbol_toggle(session, state, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] symbol_toggle {sym} error: {exc}")
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
        print(f"[TG] handler {data} error: {exc}")
        result = f"Ошибка обработчика: {exc}"

    if isinstance(result, tuple) and len(result) == 2:
        text, keyboard = result
    else:
        text = result
        keyboard = set_keyboard()

    if cb_id:
        await answer_callback(session, cb_id, "Готово")
    await send_message(session, text, reply_markup=keyboard)




# ─── Text commands ────────────────────────────────────────────────────

async def _process_message(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    msg: dict[str, Any],
) -> None:
    text = (msg.get("text") or "").strip()
    lowered = text.lower()
    chat_id = (msg.get("chat") or {}).get("id", config.TELEGRAM_CHAT_ID)
    message_id = msg.get("message_id")

    if lowered in ("/start", "/menu", "/help"):
        await send_message(
            session,
            _card("Zenith Funding Arbitrage", "\U0001f44b", [
                "8 бирж: Bybit OKX Binance Gate",
                "        Bitget MEXC HTX BingX",
                "",
                "Кнопки:",
                "  Статус    - сводка по арб-сделкам",
                "  Фандинг   - текущий funding-скан",
                "  Пары      - детали открытых связок",
                "  Балансы   - отчёт executor'а",
                "  Символы   - вкл/выкл символы скана",
                "  Биржи     - вкл/выкл биржи",
                "  AI        - статус AI-модулей",
                "  Ключи     - API-ключи",
                "  PANIC     - закрыть все позиции",
                "  Kill      - kill-switch статус",
                "",
                "Текстовые команды:",
                "  /status /arb_status /funding",
                "  /exchanges /resume_kill_switch",
                "  /setkey ИМЯ значение",
                "  /delkey ИМЯ",
            ]),
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
        txt, keyboard = await _handle_exchanges(session, state)
        await send_message(session, txt, reply_markup=keyboard)
        return

    if lowered == "/arb_status":
        await send_message(
            session,
            arb_executor.format_status(),
            reply_markup=set_keyboard(),
        )
        return

    # /setkey ИМЯ значение — с автоудалением сообщения через 30с
    if lowered.startswith("/setkey "):
        parts = text.split(None, 2)
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
                _card("Ключ обновлён", "\U0001f511", [
                    f"{key_name} применён немедленно.",
                    "",
                    "Сообщение с ключом будет удалено через 30 сек.",
                ]),
                reply_markup=set_keyboard(),
            )
        except ValueError as exc:
            await send_message(
                session, f"\u274c Ошибка: {exc}", reply_markup=set_keyboard()
            )
            return

        # Автоудаление сообщения пользователя через 30с
        if message_id and chat_id:
            async def _delayed_delete() -> None:
                await asyncio.sleep(30)
                await _delete_message(session, chat_id, message_id)
            asyncio.ensure_future(_delayed_delete())
        return

    # /delkey ИМЯ
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
                _card("Ключ сброшен", "\U0001f511", [
                    f"Оверрайд {key_name} удалён.",
                    "Используется Replit-секрет (если задан).",
                ]),
                reply_markup=set_keyboard(),
            )
        else:
            await send_message(
                session,
                f"\u2139\ufe0f Оверрайда для <b>{key_name}</b> не было.",
                reply_markup=set_keyboard(),
            )
        return

    # Любое другое сообщение
    await send_message(
        session,
        "Используйте кнопки ниже для управления.",
        reply_markup=set_keyboard(),
    )




# ─── Long-polling loop ────────────────────────────────────────────────

async def run_bot(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Основной long-polling цикл Telegram."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[TG] Bot not started: missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        while True:
            await asyncio.sleep(3600)

    print("[TG] Long-polling Telegram started")
    offset: Optional[int] = None
    while True:
        try:
            params: dict[str, Any] = {
                "timeout": 30,
                "allowed_updates": json.dumps(["message", "callback_query"]),
            }
            if offset is not None:
                params["offset"] = offset
            async with session.get(
                _bot_url("getUpdates"), params=params, timeout=40
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[TG] getUpdates status {resp.status}: {body[:200]}")
                    await asyncio.sleep(5)
                    continue
                data = await resp.json()
        except aiohttp.ClientError as exc:
            print(f"[TG] network error getUpdates: {exc}")
            await asyncio.sleep(5)
            continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[TG] unexpected error getUpdates: {exc}")
            await asyncio.sleep(5)
            continue

        if not data.get("ok"):
            print(f"[TG] Telegram returned not ok: {data}")
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
                            "\u0414\u043e\u0441\u0442\u0443\u043f \u0437\u0430\u043f\u0440\u0435\u0449\u0435\u043d",
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
                print(f"[TG] update processing error: {exc}")
