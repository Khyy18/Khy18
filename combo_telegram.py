"""Telegram-терминал КОМБО-бота (funding + grid + momentum).

Единый интерфейс управления всеми тремя стратегиями.
Long polling через aiohttp. HTML-парсинг. Русский UI.

Кнопки:
  [▪ Статус] [📡 Funding] [▪ Grid] [📈 Momentum]
  [⚙️ Allocate] [🛡 Kill] [! PANIC ALL]
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import aiohttp

import capital_allocator
import combo_config as cfg
import config
import global_kill_switch
import grid_engine
import momentum_engine


# ─── Константы UI ─────────────────────────────────────────────────────

_DIVIDER = "\u2501" * 24
_THIN_SPACE = "\u202f"  # узкий неразрывный пробел для разделителя тысяч


# ─── Callback data ────────────────────────────────────────────────────

CB_STATUS = "cb:status"
CB_FUNDING = "cb:funding"
CB_GRID = "cb:grid"
CB_MOMENTUM = "cb:momentum"
CB_ALLOCATE = "cb:alloc"
CB_KILL = "cb:kill"
CB_PANIC_ALL = "cb:panic"
CB_PANIC_CONFIRM = "cb:panic_ok"
CB_PANIC_CANCEL = "cb:panic_no"
CB_KILL_RESUME = "cb:kill_resume"
CB_KILL_RESUME_OK = "cb:kill_res_ok"
CB_KILL_RESUME_NO = "cb:kill_res_no"
CB_GRID_START = "cb:grid_on"
CB_GRID_STOP = "cb:grid_off"
CB_MOM_START = "cb:mom_on"
CB_MOM_STOP = "cb:mom_off"


# ─── Helper: _card ────────────────────────────────────────────────────

def _card(title: str, emoji: str, body_lines: list[str], footer: str = "") -> str:
    """Универсальная моноширинная карточка.

    Формат:
      {emoji} <b>{title}</b>
      ━━━━━━━━━━━━━━━━━━━━━━━━
      <pre>
      {body}
      </pre>
      <i>{footer}</i>
    """
    header = f"{emoji} <b>{title}</b>"
    body = "\n".join(body_lines)
    parts = [header, _DIVIDER, f"<pre>{body}</pre>"]
    if footer:
        parts.append(f"<i>{footer}</i>")
    return "\n".join(parts)


def _fmt_num(value: float, decimals: int = 2) -> str:
    """Форматировать число с разделителем тысяч (узкий пробел)."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", _THIN_SPACE)


def _progress_bar(value: float, total: float, width: int = 10) -> str:
    """Прогресс-бар через ▰▱."""
    if total <= 0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, value / total))
    filled = round(ratio * width)
    return "\u25b0" * filled + "\u25b1" * (width - filled)


def _sparkline(values: list[float], width: int = 8) -> str:
    """Sparkline из последних N значений через ▁▂▃▄▅▆▇█."""
    chars = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    # Берём последние width значений
    recent = values[-width:]
    if len(recent) < 2:
        return chars[4] * len(recent)
    mn = min(recent)
    mx = max(recent)
    rng = mx - mn
    if rng == 0:
        return chars[4] * len(recent)
    result = ""
    for v in recent:
        idx = int((v - mn) / rng * (len(chars) - 1))
        result += chars[max(0, min(len(chars) - 1, idx))]
    return result


def _regime_icon(regime: str) -> str:
    """Иконка режима рынка."""
    icons = {
        "TRENDING": "\U0001f9e0 TRENDING \u2197",
        "RANGING": "\U0001f4ca RANGING \u2194",
        "VOLATILE": "\u26a1 VOLATILE",
    }
    return icons.get(regime, "\u2753 ???")


def _grid_bar(active: int, total: int, width: int = 10) -> str:
    """Визуальная полоса заполнения grid: ████░░░░░░."""
    if total <= 0:
        return "\u2591" * width
    filled = round(active / total * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


# ─── Клавиатура ───────────────────────────────────────────────────────

def combo_keyboard() -> dict[str, Any]:
    """Главная инлайн-клавиатура combo-бота."""
    return {
        "inline_keyboard": [
            [
                {"text": "▪ Статус", "callback_data": CB_STATUS},
                {"text": "\U0001f4e1 Funding", "callback_data": CB_FUNDING},
            ],
            [
                {"text": "▪ Grid", "callback_data": CB_GRID},
                {"text": "\U0001f4c8 Momentum", "callback_data": CB_MOMENTUM},
            ],
            [
                {"text": "\u2699\ufe0f Allocate", "callback_data": CB_ALLOCATE},
                {"text": "\U0001f6e1 Kill", "callback_data": CB_KILL},
            ],
            [
                {"text": "\u203c PANIC ALL", "callback_data": CB_PANIC_ALL},
            ],
        ]
    }


# ─── Telegram API helpers ─────────────────────────────────────────────

def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def send_message(
    session: aiohttp.ClientSession,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
    chat_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram."""
    if not config.TELEGRAM_TOKEN:
        return None
    payload: dict[str, Any] = {
        "chat_id": chat_id or config.TELEGRAM_CHAT_ID,
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
                print(f"[COMBO-TG] sendMessage {resp.status}: {body[:200]}")
                return None
            return await resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO-TG] sendMessage error: {exc}")
        return None


async def answer_callback(
    session: aiohttp.ClientSession,
    callback_id: str,
    text: str = "",
) -> None:
    """answerCallbackQuery."""
    if not config.TELEGRAM_TOKEN:
        return
    payload = {
        "callback_query_id": callback_id,
        "text": text[:200],
    }
    try:
        async with session.post(
            _bot_url("answerCallbackQuery"), data=payload, timeout=10
        ) as resp:
            if resp.status != 200:
                pass
    except Exception:  # noqa: BLE001
        pass


# ─── Auth ─────────────────────────────────────────────────────────────

def _is_authorized(update: dict[str, Any]) -> bool:
    """True только для разрешённого chat_id."""
    allowed = config.TELEGRAM_CHAT_ID
    if not allowed:
        return False
    try:
        msg = update.get("message") or update.get("edited_message")
        if msg:
            return (msg.get("chat") or {}).get("id") == allowed
        cb = update.get("callback_query")
        if cb:
            return ((cb.get("message") or {}).get("chat") or {}).get("id") == allowed
    except Exception:  # noqa: BLE001
        pass
    return False



# ─── Обработчики кнопок ───────────────────────────────────────────────

async def _handle_status(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Общий статус: equity, drawdown, все стратегии."""
    summary = capital_allocator.get_allocation_summary(state)
    ks = global_kill_switch.get_status(state)

    # Статус-индикаторы
    kill_icon = "\U0001f534" if ks["active"] else "\U0001f7e2"
    grid_icon = "\U0001f7e2" if state.get("grid", {}).get("enabled") else "\u26aa"
    mom_icon = "\U0001f7e2" if state.get("momentum", {}).get("enabled") else "\u26aa"
    fund_icon = "\U0001f7e2" if state.get("global", {}).get("bot_running", True) else "\u26aa"

    equity = summary["current_equity"]
    dd = summary["drawdown_pct"]
    hwm = summary["hwm"]

    # Режим рынка
    g = state.get("global", {})
    regime = g.get("current_regime", "")
    regime_line = _regime_icon(regime) if regime else ""

    body = [
        f"Equity:    ${_fmt_num(equity)}",
        f"HWM:       ${_fmt_num(hwm)}",
        f"Drawdown:  {dd*100:.1f}% {_progress_bar(dd, cfg.GLOBAL_MAX_DRAWDOWN_PCT)}",
        f"Kill порог: {cfg.GLOBAL_MAX_DRAWDOWN_PCT*100:.0f}%",
    ]

    if regime_line:
        body.append(f"Режим:     {regime_line}")

    body += [
        "",
        f"{kill_icon} Kill-switch: {'АКТИВЕН' if ks['active'] else 'выкл'}",
        "",
        "\u2500\u2500 Стратегии \u2500\u2500",
        "",
    ]

    for name, icon, label in [
        ("funding", fund_icon, "Funding-арб"),
        ("grid", grid_icon, "Grid"),
        ("momentum", mom_icon, "Momentum"),
    ]:
        s = summary["strategies"][name]
        pnl = s["pnl"]
        alloc_pct = s["alloc_pct"] * 100
        alloc_usdt = s["alloc_usdt"]
        arrow = "\u25b2+" if pnl >= 0 else "\u25bc\u2212"
        body.append(
            f"{icon} {label:12s} {alloc_pct:.0f}% (${_fmt_num(alloc_usdt, 0)}) "
            f"{arrow}{abs(pnl):.2f}"
        )

    total_pnl = capital_allocator.get_total_pnl(state)
    total_arrow = "\u25b2+" if total_pnl >= 0 else "\u25bc\u2212"
    body.append("")
    body.append(f"Итого PnL: {total_arrow}{abs(total_pnl):.2f} USDT")

    # Sparkline PnL (из signals_history momentum)
    mom_state = state.get("momentum", {})
    signals = mom_state.get("signals_history", [])
    if signals:
        pnl_values = [float(s.get("price", 0)) for s in signals[-8:]]
        spark = _sparkline(pnl_values)
        if spark:
            body.append(f"Trend:     {spark}")

    return _card("Комбо-статус", "\U0001f4ca", body)


async def _handle_funding(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Статус funding-арбитража (делегирует в оригинальный telegram_bot)."""
    import telegram_bot as orig_tg
    try:
        return await orig_tg._handle_stats(session, state)
    except Exception as exc:  # noqa: BLE001
        return _card("Funding", "\U0001f4e1", [f"Ошибка: {exc}"])


async def _handle_grid(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Статус grid-бота."""
    status = grid_engine.get_grid_status(state)

    enabled_icon = "\U0001f7e2" if status["enabled"] else "\U0001f534"

    # Адаптивный шаг из state
    g = state.get("global", {})
    actual_step = ""
    for sym in cfg.GRID_SYMBOLS:
        sym_state = state.get("grid", {}).get("symbols", {}).get(sym, {})
        s = sym_state.get("step_pct_actual")
        if s:
            actual_step = f" (ATR: {float(s)*100:.2f}%)"
            break

    body = [
        f"Состояние: {enabled_icon} {'активен' if status['enabled'] else 'выкл'}",
        f"Биржа: {status['exchange'].upper()}",
        f"Уровней: {status['levels_per_side']} × 2 стороны",
        f"Шаг: {status['step_pct']*100:.2f}%{actual_step}",
        f"Плечо: {status['leverage']}x",
        "",
        f"Циклов завершено: {status['total_cycles']}",
        f"Profit: {status['total_profit_usdt']:+.4f} USDT",
        "",
        "\u2500\u2500 Символы \u2500\u2500",
    ]

    for sym, info in status["symbols"].items():
        short_sym = sym.replace("USDT", "")
        mid = info["mid_price"]
        active = info["active_orders"]
        total = info["total_levels"]
        bar = _grid_bar(active, total)
        body.append(
            f"  {short_sym}: {bar} {active}/{total}"
        )
        if mid > 0:
            body.append(f"       mid=${_fmt_num(mid, 1)}")

    text = _card("Grid-бот", "\u25a6", body)

    # Кнопки управления grid
    if status["enabled"]:
        kb = {"inline_keyboard": [
            [{"text": "\u23f8 Стоп Grid", "callback_data": CB_GRID_STOP}],
        ]}
    else:
        kb = {"inline_keyboard": [
            [{"text": "\u25b6\ufe0f Старт Grid", "callback_data": CB_GRID_START}],
        ]}

    return text, kb


async def _handle_momentum(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Статус momentum-стратегии."""
    status = momentum_engine.get_momentum_status(state)

    enabled_icon = "\U0001f7e2" if status["enabled"] else "\U0001f534"
    body = [
        f"Состояние: {enabled_icon} {'активен' if status['enabled'] else 'выкл'}",
        f"Биржа: {status['exchange'].upper()}",
        f"EMA: {status['ema_fast']}/{status['ema_slow']} ({status['timeframe']}m)",
        f"Плечо: {status['leverage']}x",
        f"Макс позиций: {status['max_positions']}",
        "",
        f"Сделок: {status['total_trades']}",
        f"Profit: {status['total_profit_usdt']:+.4f} USDT",
    ]

    # Открытые позиции
    open_pos = status["open_positions"]
    if open_pos:
        body.append("")
        body.append("── Открытые ──")
        for p in open_pos:
            side = p["side"]
            sym = p["symbol"].replace("USDT", "")
            entry = float(p["entry_price"])
            direction = "LONG \u2197" if side == "LONG" else "SHORT \u2198"
            held_h = (time.time() - float(p.get("opened_epoch", 0))) / 3600
            body.append(
                f"  {sym} {direction} @{entry:.2f} ({held_h:.1f}ч)"
            )
    else:
        body.append("")
        body.append("Открытых позиций нет.")

    # Последние сигналы
    signals = status.get("signals_history", [])[-5:]
    if signals:
        body.append("")
        body.append("── Сигналы ──")
        for s in reversed(signals):
            sym = s["symbol"].replace("USDT", "")
            sig = s["signal"]
            price = s["price"]
            arrow = "\u2197" if sig == "LONG" else "\u2198"
            body.append(f"  {sym} {sig} {arrow} @{price:.2f}")

    text = _card("Momentum", "\U0001f4c8", body)

    if status["enabled"]:
        kb = {"inline_keyboard": [
            [{"text": "\u23f8 Стоп Momentum", "callback_data": CB_MOM_STOP}],
        ]}
    else:
        kb = {"inline_keyboard": [
            [{"text": "\u25b6\ufe0f Старт Momentum", "callback_data": CB_MOM_START}],
        ]}

    return text, kb


async def _handle_allocate(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать текущую аллокацию капитала."""
    summary = capital_allocator.get_allocation_summary(state)
    equity = summary["current_equity"]

    body = [
        f"Общий equity: ${_fmt_num(equity)}",
        "",
        "── Распределение ──",
        "",
    ]

    for name, label in [
        ("funding", "Funding"),
        ("grid", "Grid"),
        ("momentum", "Momentum"),
    ]:
        s = summary["strategies"][name]
        pct = s["alloc_pct"] * 100
        usdt = s["alloc_usdt"]
        bar = _progress_bar(s["alloc_pct"], 1.0)
        body.append(f"  {label:10s} {pct:5.1f}% ${_fmt_num(usdt, 0)} {bar}")

    body.append("")
    body.append("Изменить: отправьте команду")
    body.append("/alloc 50 30 20")
    body.append("(funding grid momentum, в %)")

    return _card("Аллокация", "\u2699\ufe0f", body)


async def _handle_kill(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Статус kill-switch + кнопка снятия."""
    ks = global_kill_switch.get_status(state)

    body = [
        f"Активен: {'ДА' if ks['active'] else 'нет'}",
        f"Drawdown: {ks['drawdown_pct']*100:.1f}%",
        f"Порог: {ks['threshold_pct']*100:.0f}%",
        f"До порога: {ks['margin_to_kill']*100:.1f}%",
        f"Equity: ${_fmt_num(ks['equity'])}",
        f"HWM: ${_fmt_num(ks['hwm'])}",
    ]
    if ks["reason"]:
        body.append(f"Причина: {ks['reason']}")

    text = _card("Kill-Switch", "\U0001f6e1", body)

    if ks["active"]:
        kb = {"inline_keyboard": [
            [{"text": "\u2705 Снять kill-switch", "callback_data": CB_KILL_RESUME}],
        ]}
    else:
        kb = combo_keyboard()

    return text, kb


async def _handle_panic_all(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """PANIC ALL — подтверждение."""
    body = [
        "ВСЕ стратегии будут остановлены:",
        "  - Funding: close всех арб-пар",
        "  - Grid: отмена всех ордеров",
        "  - Momentum: close всех позиций",
        "",
        "Kill-switch будет активирован.",
        "Подтвердите действие.",
    ]
    text = _card("PANIC ALL", "\U0001f6a8", body)
    kb = {"inline_keyboard": [
        [
            {"text": "\u26a0\ufe0f ДА, СТОП ВСЕ", "callback_data": CB_PANIC_CONFIRM},
            {"text": "Отмена", "callback_data": CB_PANIC_CANCEL},
        ]
    ]}
    return text, kb


async def _handle_panic_confirm(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Выполнить PANIC ALL."""
    results: list[str] = []

    # 1. Активируем kill-switch
    global_kill_switch.manual_activate(state, "PANIC ALL из Telegram")
    results.append("Kill-switch активирован")

    # 2. Стоп grid
    try:
        msg = await grid_engine.stop_grid(session, state)
        results.append(f"Grid: {msg}")
    except Exception as exc:  # noqa: BLE001
        results.append(f"Grid: ошибка — {exc}")

    # 3. Стоп momentum
    try:
        msg = await momentum_engine.stop_momentum(session, state)
        results.append(f"Momentum: {msg}")
    except Exception as exc:  # noqa: BLE001
        results.append(f"Momentum: ошибка — {exc}")

    # 4. Стоп funding (через оригинальный бот)
    try:
        state.setdefault("global", {})["bot_running"] = False
        results.append("Funding: сканер остановлен")
    except Exception as exc:  # noqa: BLE001
        results.append(f"Funding: ошибка — {exc}")

    return _card("PANIC ALL выполнен", "\U0001f6a8", results,
                 footer="Для возобновления снимите kill-switch.")


async def _handle_panic_cancel(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return _card("Отменено", "\u2705", ["Ничего не тронуто."])


async def _handle_kill_resume(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Подтверждение снятия kill-switch."""
    ks = global_kill_switch.get_status(state)
    body = [
        f"Текущий drawdown: {ks['drawdown_pct']*100:.1f}%",
        f"Порог: {ks['threshold_pct']*100:.0f}%",
        "",
        "HWM будет сброшен на текущий equity.",
        "Стратегии возобновят работу.",
        "",
        "Вы уверены?",
    ]
    text = _card("Снять Kill-Switch", "\u2705", body)
    kb = {"inline_keyboard": [
        [
            {"text": "\u2705 ДА, СНЯТЬ", "callback_data": CB_KILL_RESUME_OK},
            {"text": "Отмена", "callback_data": CB_KILL_RESUME_NO},
        ]
    ]}
    return text, kb


async def _handle_kill_resume_ok(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    msg = global_kill_switch.manual_resume(state)
    return _card("Kill-switch снят", "\u2705", [msg])


async def _handle_kill_resume_no(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    return _card("Отменено", "\u2139", ["Kill-switch остаётся активным."])


async def _handle_grid_start(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    msg = await grid_engine.start_grid(state)
    return _card("Grid", "\u25b6\ufe0f", [msg])


async def _handle_grid_stop(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    msg = await grid_engine.stop_grid(session, state)
    return _card("Grid", "\u23f8", [msg])


async def _handle_mom_start(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    msg = await momentum_engine.start_momentum(state)
    return _card("Momentum", "\u25b6\ufe0f", [msg])


async def _handle_mom_stop(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    msg = await momentum_engine.stop_momentum(session, state)
    return _card("Momentum", "\u23f8", [msg])



# ─── Обработка текстовых команд ───────────────────────────────────────

async def _handle_text_command(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    text: str,
) -> Optional[str]:
    """Обработать текстовую команду (например /alloc 50 30 20)."""
    text = text.strip()

    if text.startswith("/alloc"):
        parts = text.split()
        if len(parts) != 4:
            return _card("Ошибка", "\u26a0\ufe0f", [
                "Формат: /alloc F G M",
                "Пример: /alloc 50 30 20",
                "(funding grid momentum в %)",
            ])
        try:
            f_pct = float(parts[1]) / 100
            g_pct = float(parts[2]) / 100
            m_pct = float(parts[3]) / 100
        except ValueError:
            return _card("Ошибка", "\u26a0\ufe0f", ["Значения должны быть числами."])

        err = capital_allocator.set_allocation(state, f_pct, g_pct, m_pct)
        if err:
            return _card("Ошибка", "\u26a0\ufe0f", [err])

        return _card("Аллокация обновлена", "\u2705", [
            f"Funding:  {f_pct*100:.0f}%",
            f"Grid:     {g_pct*100:.0f}%",
            f"Momentum: {m_pct*100:.0f}%",
        ])

    if text in ("/start", "/help", "/menu"):
        return _card("Комбо-бот", "\U0001f916", [
            "Funding-арб + Grid + Momentum",
            "",
            "Используйте кнопки ниже.",
            "Команды: /alloc F G M",
        ])

    return None


# ─── Handler dispatch ─────────────────────────────────────────────────

_SIMPLE_HANDLERS = {
    CB_STATUS: _handle_status,
    CB_FUNDING: _handle_funding,
    CB_PANIC_CONFIRM: _handle_panic_confirm,
    CB_PANIC_CANCEL: _handle_panic_cancel,
    CB_KILL_RESUME_OK: _handle_kill_resume_ok,
    CB_KILL_RESUME_NO: _handle_kill_resume_no,
    CB_GRID_START: _handle_grid_start,
    CB_GRID_STOP: _handle_grid_stop,
    CB_MOM_START: _handle_mom_start,
    CB_MOM_STOP: _handle_mom_stop,
}

_TUPLE_HANDLERS = {
    CB_GRID: _handle_grid,
    CB_MOMENTUM: _handle_momentum,
    CB_ALLOCATE: _handle_allocate,
    CB_KILL: _handle_kill,
    CB_PANIC_ALL: _handle_panic_all,
    CB_KILL_RESUME: _handle_kill_resume,
}


async def process_update(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    update: dict[str, Any],
) -> None:
    """Обработать один Telegram update."""
    if not _is_authorized(update):
        return

    # Текстовые сообщения
    msg = update.get("message")
    if msg and msg.get("text"):
        text = msg["text"]
        response = await _handle_text_command(session, state, text)
        if response:
            await send_message(session, response, reply_markup=combo_keyboard())
        elif text.startswith("/"):
            await send_message(
                session,
                _card("Комбо-бот", "\U0001f916", ["Неизвестная команда. /help"]),
                reply_markup=combo_keyboard(),
            )
        else:
            # Любое сообщение — показываем меню
            await send_message(
                session,
                _card("Комбо-бот", "\U0001f916", ["Используйте кнопки ниже."]),
                reply_markup=combo_keyboard(),
            )
        return

    # Callback query (кнопки)
    cb = update.get("callback_query")
    if not cb:
        return

    cb_id = cb.get("id")
    data = cb.get("data", "")

    if cb_id:
        await answer_callback(session, cb_id, "")

    # Simple handlers (возвращают str)
    if data in _SIMPLE_HANDLERS:
        handler = _SIMPLE_HANDLERS[data]
        try:
            result = await handler(session, state)
            await send_message(session, result, reply_markup=combo_keyboard())
        except Exception as exc:  # noqa: BLE001
            print(f"[COMBO-TG] handler {data} error: {exc}")
            await send_message(
                session, f"Ошибка: {exc}", reply_markup=combo_keyboard()
            )
        return

    # Tuple handlers (возвращают (str, keyboard))
    if data in _TUPLE_HANDLERS:
        handler = _TUPLE_HANDLERS[data]
        try:
            result = await handler(session, state)
            if isinstance(result, tuple):
                text_resp, kb = result
                await send_message(session, text_resp, reply_markup=kb)
            else:
                await send_message(session, result, reply_markup=combo_keyboard())
        except Exception as exc:  # noqa: BLE001
            print(f"[COMBO-TG] handler {data} error: {exc}")
            await send_message(
                session, f"Ошибка: {exc}", reply_markup=combo_keyboard()
            )
        return

    # Неизвестная кнопка
    await send_message(
        session,
        _card("?", "\u2753", [f"Неизвестная команда: {data}"]),
        reply_markup=combo_keyboard(),
    )


# ─── Long-polling loop ────────────────────────────────────────────────

async def polling_loop(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Long-polling цикл Telegram. Запускается как asyncio.Task."""
    offset = 0
    while True:
        try:
            params = {"offset": offset, "timeout": 30}
            async with session.get(
                _bot_url("getUpdates"), params=params, timeout=35
            ) as resp:
                if resp.status != 200:
                    await _async_sleep(5)
                    continue
                data = await resp.json()

            updates = data.get("result", [])
            for upd in updates:
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                try:
                    await process_update(session, state, upd)
                except Exception as exc:  # noqa: BLE001
                    print(f"[COMBO-TG] process_update error: {exc}")

        except Exception as exc:  # noqa: BLE001
            print(f"[COMBO-TG] polling error: {exc}")
            await _async_sleep(5)


async def _async_sleep(seconds: float) -> None:
    """asyncio.sleep обёртка."""
    import asyncio
    await asyncio.sleep(seconds)
