"""Telegram-терминал для арбитражного бота.

Long polling через aiohttp напрямую (без python-telegram-bot).
Авторизация по chat_id. HTML parse_mode, inline keyboards.
Визуальный стиль: моноширинные блоки (pre), сепараторы (24x),
U+202F для чисел, прогресс-бары (10 символов), PnL-стрелки.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from arbitrage import config, memory
from arbitrage.utils import (
    SEPARATOR,
    _card,
    format_number,
    pnl_arrow,
    progress_bar,
)


# --- Callback data ids ---
CB_SCANNER_ON: str = "arb:scan_on"
CB_SCANNER_OFF: str = "arb:scan_off"
CB_STATS: str = "arb:stats"
CB_ACTIVE: str = "arb:active"
CB_BANK: str = "arb:bank"
CB_SETTINGS: str = "arb:settings"
CB_LAST_BETS: str = "arb:bets"
CB_AI_LEARNINGS: str = "arb:learnings"
CB_API_HEALTH: str = "arb:api_health"
CB_AI_FORECAST: str = "arb:ai_forecast"
CB_WITHDRAWAL: str = "arb:withdrawal"
CB_MIDDLES: str = "arb:middles"
CB_STEAM: str = "arb:steam"


def set_keyboard() -> dict[str, Any]:
    """Инлайн-клавиатура с кнопками управления (4 строки по 2)."""
    return {
        "inline_keyboard": [
            [
                {"text": "\u25b6\ufe0f \u0421\u041a\u0410\u041d\u0415\u0420 \u0412\u041a\u041b", "callback_data": CB_SCANNER_ON},
                {"text": "\u23f8 \u0421\u041a\u0410\u041d\u0415\u0420 \u0412\u042b\u041a\u041b", "callback_data": CB_SCANNER_OFF},
            ],
            [
                {"text": "\ud83d\udcca \u0421\u0422\u0410\u0422\u0418\u0421\u0422\u0418\u041a\u0410", "callback_data": CB_STATS},
                {"text": "\ud83d\udcc2 \u0410\u041a\u0422\u0418\u0412\u041d\u042b\u0415 \u0410\u0420\u0411\u042b", "callback_data": CB_ACTIVE},
            ],
            [
                {"text": "\ud83d\udcb0 \u0411\u0410\u041d\u041a", "callback_data": CB_BANK},
                {"text": "\ud83d\udcdd \u041f\u041e\u0421\u041b\u0415\u0414\u041d\u0418\u0415 \u0421\u0422\u0410\u0412\u041a\u0418", "callback_data": CB_LAST_BETS},
            ],
            [
                {"text": "\ud83e\udde0 AI LEARNINGS", "callback_data": CB_AI_LEARNINGS},
                {"text": "\ud83d\udce1 API HEALTH", "callback_data": CB_API_HEALTH},
            ],
            [
                {"text": "\U0001f52e AI \u041f\u0420\u041e\u0413\u041d\u041e\u0417", "callback_data": CB_AI_FORECAST},
                {"text": "\U0001f4b8 \u0421\u0422\u0420\u0410\u0422\u0415\u0413\u0418\u042f \u0412\u042b\u0412\u041e\u0414\u0410", "callback_data": CB_WITHDRAWAL},
            ],
            [
                {"text": "\U0001f3af \u041a\u041e\u0420\u0418\u0414\u041e\u0420\u042b", "callback_data": CB_MIDDLES},
                {"text": "\u26a1 STEAM", "callback_data": CB_STEAM},
            ],
        ]
    }


def _bot_url(method: str) -> str:
    """URL для вызова метода Telegram Bot API."""
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def send_message(
    session: aiohttp.ClientSession,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
    chat_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Отправить сообщение в Telegram. HTML parse_mode."""
    if not config.TELEGRAM_TOKEN:
        print("[ARB_TG] TELEGRAM_TOKEN не задан - пропускаем отправку")
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
                print(f"[ARB_TG] sendMessage статус {resp.status}: {body[:200]}")
                return None
            return await resp.json()
    except aiohttp.ClientError as exc:
        print(f"[ARB_TG] Сетевая ошибка sendMessage: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB_TG] Неожиданная ошибка sendMessage: {exc}")
        return None


async def answer_callback(
    session: aiohttp.ClientSession,
    callback_id: str,
    text: str = "",
) -> None:
    """answerCallbackQuery - убирает часики у нажатой кнопки."""
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
                body = await resp.text()
                print(f"[ARB_TG] answerCallbackQuery статус {resp.status}: {body[:200]}")
    except aiohttp.ClientError as exc:
        print(f"[ARB_TG] Сетевая ошибка answerCallbackQuery: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB_TG] Неожиданная ошибка answerCallbackQuery: {exc}")


def _is_authorized(update: dict[str, Any]) -> bool:
    """True только если from.id и chat.id совпадают с TELEGRAM_CHAT_ID."""
    allowed = config.TELEGRAM_CHAT_ID
    if not allowed:
        return False
    try:
        allowed_int = int(allowed)
    except (TypeError, ValueError):
        return False

    try:
        msg = update.get("message") or update.get("edited_message")
        if msg:
            from_id = (msg.get("from") or {}).get("id")
            chat_id = (msg.get("chat") or {}).get("id")
            return from_id == allowed_int and chat_id == allowed_int
        cb = update.get("callback_query")
        if cb:
            from_id = (cb.get("from") or {}).get("id")
            chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
            if chat_id is None:
                return from_id == allowed_int
            return from_id == allowed_int and chat_id == allowed_int
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB_TG] Ошибка проверки авторизации: {exc}")
    return False


# --- Обработчики кнопок ---


async def _handle_scanner_on(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    state["scanner_active"] = True
    return "\u2705 Сканер <b>запущен</b>. Поиск арбитражей активен."


async def _handle_scanner_off(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    state["scanner_active"] = False
    return "\u23f8 Сканер <b>остановлен</b>. Поиск арбитражей приостановлен."


async def _handle_stats(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    stats = memory.get_stats()
    total_arbs = stats.get("total_arbs", 0)
    executed = stats.get("executed_arbs", 0)
    total_bets = stats.get("total_bets", 0)
    won = stats.get("won_bets", 0)
    lost = stats.get("lost_bets", 0)
    total_pnl = stats.get("total_pnl", 0.0)

    win_rate = (won / total_bets * 100.0) if total_bets > 0 else 0.0
    roi = (total_pnl / max(executed, 1)) * 100.0 if executed > 0 else 0.0

    body = [
        f"Найдено арбитражей: <code>{format_number(total_arbs)}</code>",
        f"Исполнено: <code>{format_number(executed)}</code>",
        f"Всего ставок: <code>{format_number(total_bets)}</code>",
        f"Побед / Поражений: <code>{won}</code> / <code>{lost}</code>",
        f"Винрейт: <code>{win_rate:.1f}%</code>",
        f"ROI: {pnl_arrow(roi)}",
        f"Суммарный PnL: {pnl_arrow(total_pnl)}",
    ]

    # CLV статистика
    clv_stats = state.get("clv_stats", {})
    avg_clv = clv_stats.get("avg_clv_pct", 0.0)
    clv_positive = clv_stats.get("positive_count", 0)
    clv_negative = clv_stats.get("negative_count", 0)
    clv_total = clv_stats.get("total_checked", 0)
    if clv_total > 0:
        body.append(f"CLV: <code>{avg_clv:.2f}%</code> (+{clv_positive}/-{clv_negative})")

    # Breakdown по типам
    middles_count = len(state.get("middles_opps", []))
    steam_count = len(state.get("steam_opps", []))
    body.append(
        f"\u0422\u0438\u043f\u044b: surebets/value | middles: {middles_count} | steam: {steam_count}"
    )

    # Дневная статистика PnL за 7 дней
    daily_pnl = memory.get_daily_pnl(7)
    if daily_pnl:
        body.append("")
        body.append("<b>PnL за 7 дней:</b>")
        for day in daily_pnl:
            date_str = day.get("date", "?")
            day_pnl = day.get("pnl", 0.0)
            day_roi = day.get("roi_pct", 0.0)
            body.append(f"  {date_str}: {pnl_arrow(day_pnl)} (ROI {day_roi:.1f}%)")

    return _card("\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430", "\ud83d\udcca", body)


async def _handle_active(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    arbs = memory.get_active_arbs()
    if not arbs:
        return _card("\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0430\u0440\u0431\u0438\u0442\u0440\u0430\u0436\u0438", "\ud83d\udcc2", ["\u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0430\u0440\u0431\u0438\u0442\u0440\u0430\u0436\u0435\u0439"])

    body: list[str] = []
    for arb in arbs[:10]:
        sport = arb.get("sport", "?")
        event = arb.get("event", "?")
        profit = arb.get("profit_pct", 0.0)
        ai_score = arb.get("ai_score", 0)
        body.append(
            f"\u2022 <code>{sport}</code> | {event}\n"
            f"  \u0414\u043e\u0445\u043e\u0434: <code>{profit:.2f}%</code> | AI: {progress_bar(ai_score / 100.0)} {ai_score}"
        )
    return _card("\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0430\u0440\u0431\u0438\u0442\u0440\u0430\u0436\u0438", "\ud83d\udcc2", body)


async def _handle_bank(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    bankroll = state.get("bankroll", 0.0)
    exposure = state.get("exposure", 0.0)
    available = bankroll - exposure

    body = [
        f"\u0411\u0430\u043d\u043a\u0440\u043e\u043b\u043b: <code>{format_number(bankroll)}</code>",
        f"\u042d\u043a\u0441\u043f\u043e\u0437\u0438\u0446\u0438\u044f: <code>{format_number(exposure)}</code>",
        f"\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u043e: <code>{format_number(available)}</code>",
        f"\u041c\u0430\u043a\u0441. \u044d\u043a\u0441\u043f\u043e\u0437\u0438\u0446\u0438\u044f: <code>{config.MAX_BANKROLL_EXPOSURE}%</code>",
    ]

    # Балансы БК
    balances = memory.get_all_account_balances()
    if balances:
        body.append("")
        body.append("<b>Балансы БК:</b>")
        for acc in balances:
            body.append(f"  {acc['bookmaker']}: <code>{format_number(acc['balance'])}</code>")

    # Классификации рисков БК
    classifications = memory.get_all_bk_classifications()
    if classifications:
        body.append("")
        body.append("<b>\u0420\u0438\u0441\u043a\u0438 \u0411\u041a:</b>")
        for cls in classifications:
            risk = cls.get("risk_level", "medium")
            if risk == "low":
                indicator = "\ud83d\udfe2"
            elif risk == "medium":
                indicator = "\ud83d\udfe1"
            elif risk == "high":
                indicator = "\ud83d\udd34"
            else:
                indicator = "\u2620\ufe0f"
            body.append(
                f"  {indicator} {cls['bookmaker']}: <code>{risk}</code>"
            )

    return _card("\u0411\u0430\u043d\u043a", "\ud83d\udcb0", body)


async def _handle_settings(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    dry_status = "\ud83d\udfe2 DRY RUN" if config.DRY_RUN else "\ud83d\udd34 LIVE"
    body = [
        f"MIN_ARB_PROFIT: <code>{config.MIN_ARB_PROFIT}%</code>",
        f"MIN_VALUE_EDGE: <code>{config.MIN_VALUE_EDGE}%</code>",
        f"SCAN_INTERVAL: <code>{config.SCAN_INTERVAL_SEC} \u0441\u0435\u043a</code>",
        f"MAX_BET_PCT: <code>{config.MAX_BET_PCT}%</code>",
        f"\u0420\u0435\u0436\u0438\u043c: {dry_status}",
        f"\u0421\u043f\u043e\u0440\u0442\u044b: <code>{', '.join(config.SPORTS)}</code>",
    ]

    # Auto-optimized thresholds
    defaults = {"MIN_ARB_PROFIT": 1.0, "MIN_VALUE_EDGE": 3.0, "SCAN_INTERVAL_SEC": 30}
    current = {
        "MIN_ARB_PROFIT": config.MIN_ARB_PROFIT,
        "MIN_VALUE_EDGE": config.MIN_VALUE_EDGE,
        "SCAN_INTERVAL_SEC": config.SCAN_INTERVAL_SEC,
    }
    changed = {k: v for k, v in current.items() if v != defaults[k]}
    if changed:
        body.append("")
        body.append("<b>\u0410\u0432\u0442\u043e-\u043e\u043f\u0442\u0438\u043c\u0438\u0437\u0430\u0446\u0438\u044f:</b>")
        for k, v in changed.items():
            body.append(f"  {k}: <code>{v}</code> (\u0434\u0435\u0444\u043e\u043b\u0442: {defaults[k]})")

    return _card("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", "\u2699\ufe0f", body)


async def _handle_last_bets(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    bets = memory.get_recent_bets(10)
    if not bets:
        return _card("\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0441\u0442\u0430\u0432\u043a\u0438", "\ud83d\udcdd", ["\u0421\u0442\u0430\u0432\u043e\u043a \u043f\u043e\u043a\u0430 \u043d\u0435\u0442"])

    body: list[str] = []
    for bet in bets:
        result = bet.get("result", "PENDING")
        if result == "WON":
            indicator = "\ud83d\udfe2"
        elif result == "LOST":
            indicator = "\ud83d\udd34"
        else:
            indicator = "\ud83d\udfe1"
        pnl = bet.get("pnl") or 0.0
        body.append(
            f"{indicator} {bet.get('bookmaker', '?')} | "
            f"{bet.get('outcome', '?')} @ {bet.get('odds', 0):.2f} | "
            f"\u0421\u0442\u0430\u0432\u043a\u0430: {format_number(bet.get('stake', 0))} | "
            f"PnL: {pnl_arrow(pnl)}"
        )
    return _card("\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0441\u0442\u0430\u0432\u043a\u0438", "\ud83d\udcdd", body)


# --- Алерт при обнаружении арбитража ---


async def send_arb_alert(
    session: aiohttp.ClientSession,
    opportunity: dict[str, Any],
    ai_score: int,
) -> None:
    """Отправить алерт о найденном арбитраже."""
    sport = opportunity.get("sport", "?")
    event_name = opportunity.get("event_name", opportunity.get("event", "?"))
    home = opportunity.get("home", "")
    away = opportunity.get("away", "")
    bookmakers = opportunity.get("bookmakers", [])
    odds = opportunity.get("odds", [])
    profit_pct = opportunity.get("profit_pct", 0.0)
    arb_type = opportunity.get("type", "surebet")

    confidence = ai_score / 100.0
    bar = progress_bar(confidence)

    body = [
        f"\u0422\u0438\u043f: <code>{arb_type}</code>",
        f"\u0421\u043f\u043e\u0440\u0442: <code>{sport}</code>",
        f"\u0421\u043e\u0431\u044b\u0442\u0438\u0435: <b>{event_name}</b>",
    ]
    if home and away:
        body.append(f"\u041a\u043e\u043c\u0430\u043d\u0434\u044b: {home} vs {away}")
    if bookmakers:
        body.append(f"\u0411\u0443\u043a\u043c\u0435\u043a\u0435\u0440\u044b: <code>{', '.join(str(b) for b in bookmakers)}</code>")
    if odds:
        body.append(f"\u041a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u044b: <code>{' / '.join(f'{o:.2f}' for o in odds)}</code>")
    body.append(f"\u041f\u0440\u0438\u0431\u044b\u043b\u044c: <code>{profit_pct:.2f}%</code>")
    body.append(f"AI Score: {bar} <code>{ai_score}/100</code>")

    text = _card("\u041d\u043e\u0432\u044b\u0439 \u0430\u0440\u0431\u0438\u0442\u0440\u0430\u0436!", "\ud83d\udea8", body)
    await send_message(session, text, reply_markup=set_keyboard())


# --- Алерты анти-бана и API ---


async def send_pre_ban_alert(
    session: aiohttp.ClientSession,
    bookmaker: str,
    detail: str,
) -> None:
    """Отправить алерт при детектировании паттерна пре-бана."""
    body = [
        f"\ud83d\udd34 <b>Букмекер:</b> <code>{bookmaker}</code>",
        f"\ud83d\udd34 <b>Детали:</b> {detail}",
        "",
        "Рекомендация: приостановить ставки у данного букмекера.",
    ]
    text = _card("\u041f\u0440\u0435-\u0431\u0430\u043d \u0434\u0435\u0442\u0435\u043a\u0442\u043e\u0440", "\ud83d\udea8", body)
    await send_message(session, text, reply_markup=set_keyboard())


async def send_quota_alert(
    session: aiohttp.ClientSession,
    remaining_pct: float,
    latency_ms: float,
) -> None:
    """Отправить алерт при низкой квоте API или высокой задержке."""
    body: list[str] = []

    if remaining_pct < 10.0:
        body.append(f"\ud83d\udd34 Квота API: <code>{remaining_pct:.1f}%</code> осталось")
    else:
        body.append(f"\ud83d\udfe1 Квота API: <code>{remaining_pct:.1f}%</code> осталось")

    if latency_ms > 5000:
        body.append(f"\ud83d\udd34 Задержка: <code>{latency_ms:.0f}ms</code>")
    elif latency_ms > 2000:
        body.append(f"\ud83d\udfe1 Задержка: <code>{latency_ms:.0f}ms</code>")
    else:
        body.append(f"\ud83d\udfe2 Задержка: <code>{latency_ms:.0f}ms</code>")

    body.append("")
    body.append("Рекомендация: снизить частоту сканирования.")

    text = _card("API \u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433", "\u26a0\ufe0f", body)
    await send_message(session, text, reply_markup=set_keyboard())


# --- Обработчики новых кнопок ---


async def _handle_ai_learnings(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать выученные правила AI-фильтра."""
    learnings = memory.get_ai_learnings(10)
    if not learnings:
        return _card("AI Learnings", "\ud83e\udde0", ["\u041d\u0435\u0442 \u0432\u044b\u0443\u0447\u0435\u043d\u043d\u044b\u0445 \u043f\u0440\u0430\u0432\u0438\u043b"])

    body: list[str] = []
    for rule in learnings:
        rule_type = rule.get("rule_type", "?")
        rule_text = rule.get("rule_text", "?")
        confidence = rule.get("confidence", 0.0)
        ts = rule.get("ts", "")[:10]  # только дата
        bar = progress_bar(confidence)
        body.append(
            f"\u2022 [{rule_type}] {rule_text}\n"
            f"  \u0423\u0432\u0435\u0440\u0435\u043d\u043d\u043e\u0441\u0442\u044c: {bar} <code>{confidence:.0%}</code> | {ts}"
        )
    return _card("AI Learnings", "\ud83e\udde0", body)


async def _handle_api_health(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать здоровье API (квота, задержка, ошибки)."""
    health = state.get("api_health", {})
    remaining = health.get("remaining_quota")
    used = health.get("used_quota")
    latency = health.get("last_latency_ms", 0.0)

    # Расчёт процента квоты
    if remaining is not None and used is not None:
        total = remaining + used
        remaining_pct = (remaining / total * 100.0) if total > 0 else 100.0
    else:
        remaining_pct = 100.0
        total = 0

    # Индикаторы квоты: зелёный >50%, жёлтый >10%, красный <10%
    if remaining_pct > 50.0:
        quota_indicator = "\ud83d\udfe2"
    elif remaining_pct > 10.0:
        quota_indicator = "\ud83d\udfe1"
    else:
        quota_indicator = "\ud83d\udd34"

    # Индикаторы задержки: зелёный <2с, жёлтый <5с, красный >5с
    if latency < 2000.0:
        latency_indicator = "\ud83d\udfe2"
    elif latency < 5000.0:
        latency_indicator = "\ud83d\udfe1"
    else:
        latency_indicator = "\ud83d\udd34"

    body = [
        f"{quota_indicator} Квота: <code>{remaining if remaining is not None else '?'}</code> / <code>{total if total > 0 else '?'}</code> ({remaining_pct:.1f}%)",
        f"{latency_indicator} Задержка: <code>{latency:.0f}ms</code>",
        f"Использовано: <code>{used if used is not None else '?'}</code>",
    ]

    # Прогресс-бар квоты
    bar = progress_bar(remaining_pct / 100.0)
    body.append(f"Квота: {bar}")

    return _card("API Health", "\ud83d\udce1", body)


async def _handle_ai_forecast(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать текущие AI-прогнозы движения линий."""
    predictions = state.get("line_predictions", [])
    if not predictions:
        return _card("AI \u041f\u0440\u043e\u0433\u043d\u043e\u0437", "\U0001f52e", ["\u041d\u0435\u0442 \u043f\u0440\u043e\u0433\u043d\u043e\u0437\u043e\u0432"])

    body: list[str] = []
    for pred in predictions[:5]:
        event = pred.get("event_id", "?")
        direction = pred.get("direction", "stable")
        magnitude = pred.get("magnitude", 0.0)
        confidence = pred.get("confidence", 0)
        timeframe = pred.get("timeframe_min", 15)
        if direction == "up":
            arrow = "\u2191"
        elif direction == "down":
            arrow = "\u2193"
        else:
            arrow = "\u2192"
        bar = progress_bar(confidence / 100.0)
        body.append(
            f"\u2022 <code>{event}</code>\n"
            f"  {arrow} {direction} | \u0394 {magnitude:.3f} | {bar} {confidence}% | {timeframe} \u043c\u0438\u043d"
        )
    return _card("AI \u041f\u0440\u043e\u0433\u043d\u043e\u0437", "\U0001f52e", body)


async def _handle_withdrawal(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать рекомендации по выводу средств."""
    from arbitrage.ai_withdrawal import WithdrawalStrategy

    strategy = WithdrawalStrategy()
    try:
        recommendations = await strategy.recommend(session)
    except Exception:  # noqa: BLE001
        recommendations = []

    if not recommendations:
        return _card("\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f \u0432\u044b\u0432\u043e\u0434\u0430", "\U0001f4b8", ["\u041d\u0435\u0442 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0439"])

    body: list[str] = []
    for rec in recommendations:
        bookmaker = rec.get("bookmaker", "?")
        amount = rec.get("amount", 0.0)
        reason = rec.get("reason", "")
        urgency = rec.get("urgency", "low")
        if urgency == "high":
            indicator = "\ud83d\udd34"
        elif urgency == "medium":
            indicator = "\ud83d\udfe1"
        else:
            indicator = "\ud83d\udfe2"
        body.append(
            f"{indicator} <b>{bookmaker}</b>: <code>{format_number(amount)}</code>\n"
            f"  {reason} [{urgency}]"
        )
    return _card("\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f \u0432\u044b\u0432\u043e\u0434\u0430", "\U0001f4b8", body)


async def _handle_middles(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать последние найденные коридоры (middles)."""
    middles = state.get("middles_opps", [])
    if not middles:
        return _card("\u041a\u043e\u0440\u0438\u0434\u043e\u0440\u044b", "\U0001f3af", ["\u041d\u0435\u0442 \u043d\u0430\u0439\u0434\u0435\u043d\u043d\u044b\u0445 \u043a\u043e\u0440\u0438\u0434\u043e\u0440\u043e\u0432"])

    body: list[str] = []
    for m in middles[:10]:
        event_name = getattr(m, "event_name", str(m))
        sport = getattr(m, "sport", "?")
        best_profit = getattr(m, "best_case_profit_pct", 0.0)
        ev_pct = getattr(m, "expected_value_pct", 0.0)
        mid_range = getattr(m, "middle_range", [])
        leg1 = getattr(m, "leg1", {})
        leg2 = getattr(m, "leg2", {})
        bk1 = leg1.get("bookmaker", "?") if isinstance(leg1, dict) else "?"
        bk2 = leg2.get("bookmaker", "?") if isinstance(leg2, dict) else "?"
        body.append(
            f"\u2022 <code>{sport}</code> | {event_name}\n"
            f"  \u0411\u041a: {bk1} / {bk2}\n"
            f"  \u041a\u043e\u0440\u0438\u0434\u043e\u0440: {mid_range} | "
            f"\u041f\u0440\u0438\u0431\u044b\u043b\u044c: <code>{best_profit:.2f}%</code> | "
            f"EV: <code>{ev_pct:.2f}%</code>"
        )
    return _card("\u041a\u043e\u0440\u0438\u0434\u043e\u0440\u044b", "\U0001f3af", body)


async def _handle_steam(
    session: aiohttp.ClientSession, state: dict[str, Any]
) -> str:
    """Показать последние Steam Moves."""
    steam_opps = state.get("steam_opps", [])
    if not steam_opps:
        return _card("Steam Moves", "\u26a1", ["\u041d\u0435\u0442 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043d\u044b\u0445 steam moves"])

    body: list[str] = []
    for s in steam_opps[:10]:
        event_name = getattr(s, "event_name", str(s))
        sport = getattr(s, "sport", "?")
        direction = getattr(s, "direction", "?")
        movement = getattr(s, "sharp_movement", 0.0)
        confidence = getattr(s, "confidence", 0)
        stale = getattr(s, "stale_bookmakers", [])
        stale_names = [b.get("bookmaker", "?") if isinstance(b, dict) else str(b) for b in stale[:3]]
        bar = progress_bar(confidence / 100.0)
        body.append(
            f"\u2022 <code>{sport}</code> | {event_name}\n"
            f"  {direction} \u0394{movement:.3f} | {bar} {confidence}%\n"
            f"  Stale: {', '.join(stale_names)}"
        )
    return _card("Steam Moves", "\u26a1", body)


# --- Маппинг обработчиков ---

_HANDLERS: dict[str, Any] = {
    CB_SCANNER_ON: _handle_scanner_on,
    CB_SCANNER_OFF: _handle_scanner_off,
    CB_STATS: _handle_stats,
    CB_ACTIVE: _handle_active,
    CB_BANK: _handle_bank,
    CB_SETTINGS: _handle_settings,
    CB_LAST_BETS: _handle_last_bets,
    CB_AI_LEARNINGS: _handle_ai_learnings,
    CB_API_HEALTH: _handle_api_health,
    CB_AI_FORECAST: _handle_ai_forecast,
    CB_WITHDRAWAL: _handle_withdrawal,
    CB_MIDDLES: _handle_middles,
    CB_STEAM: _handle_steam,
}


async def _process_callback(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    cb: dict[str, Any],
) -> None:
    """Обработка callback_query."""
    cb_id = cb.get("id")
    data = cb.get("data", "")
    handler = _HANDLERS.get(data)
    if not handler:
        if cb_id:
            await answer_callback(session, cb_id, "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f \u043a\u043e\u043c\u0430\u043d\u0434\u0430")
        return
    try:
        text = await handler(session, state)
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB_TG] \u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a\u0430 {data}: {exc}")
        text = f"\u041e\u0448\u0438\u0431\u043a\u0430: {exc}"

    if cb_id:
        await answer_callback(session, cb_id, "\u0413\u043e\u0442\u043e\u0432\u043e")
    await send_message(session, text, reply_markup=set_keyboard())


async def _process_message(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    msg: dict[str, Any],
) -> None:
    """Обработка текстового сообщения."""
    text = (msg.get("text") or "").strip().lower()
    if text in ("/start", "/help", "/menu"):
        await send_message(
            session,
            "\ud83c\udfaf <b>Arbitrage Bot</b>\n"
            "\u0410\u0440\u0431\u0438\u0442\u0440\u0430\u0436\u043d\u044b\u0439 \u0431\u043e\u0442 \u0434\u043b\u044f \u0441\u043f\u043e\u0440\u0442\u0438\u0432\u043d\u044b\u0445 \u0441\u0442\u0430\u0432\u043e\u043a \u0441 \u0418\u0418.\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u043a\u043d\u043e\u043f\u043a\u043e\u0439 \u043d\u0438\u0436\u0435.",
            reply_markup=set_keyboard(),
        )
        return
    if text == "/settings":
        reply = await _handle_settings(session, state)
        await send_message(session, reply, reply_markup=set_keyboard())
        return
    if text == "/news":
        findings = state.get("news_findings", [])
        if not findings:
            body_lines = ["\u041d\u0435\u0442 \u043d\u043e\u0432\u043e\u0441\u0442\u0435\u0439"]
        else:
            body_lines = []
            for item in findings[:5]:
                headline = item.get("headline", "?")
                impact = item.get("impact", "?")
                magnitude = item.get("magnitude", 0)
                confidence = item.get("confidence", 0)
                bar = progress_bar(confidence / 100.0)
                body_lines.append(
                    f"\u2022 {headline}\n"
                    f"  \u0412\u043b\u0438\u044f\u043d\u0438\u0435: {impact} | \u0421\u0438\u043b\u0430: {magnitude}/10 | {bar} {confidence}%"
                )
        reply = _card("\u041d\u043e\u0432\u043e\u0441\u0442\u0438", "\ud83d\udcf0", body_lines)
        await send_message(session, reply, reply_markup=set_keyboard())
        return
    if text.startswith("/set_balance"):
        # Формат: /set_balance pinnacle 500.0
        raw_text = (msg.get("text") or "").strip()
        parts = raw_text.split()
        if len(parts) >= 3:
            bk_name = parts[1].strip()
            try:
                amount = float(parts[2])
                memory.set_account_balance(bk_name, amount)
                reply_text = (
                    f"\u2705 Баланс <code>{bk_name}</code> установлен: "
                    f"<code>{format_number(amount)}</code>"
                )
            except (ValueError, TypeError):
                reply_text = "\u274c Неверный формат суммы. Пример: /set_balance pinnacle 500.0"
        else:
            reply_text = "\u274c Формат: /set_balance {букмекер} {сумма}"
        await send_message(session, reply_text, reply_markup=set_keyboard())
        return
    # Любое другое сообщение - показываем меню
    await send_message(
        session,
        "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0438 \u043d\u0438\u0436\u0435 \u0434\u043b\u044f \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f \u0431\u043e\u0442\u043e\u043c.",
        reply_markup=set_keyboard(),
    )


async def run_bot(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Основной long-polling цикл Telegram бота."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[ARB_TG] Бот не запущен: нет TELEGRAM_TOKEN или TELEGRAM_CHAT_ID")
        while True:
            await asyncio.sleep(3600)

    print("[ARB_TG] Long-polling Telegram запущен")
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
                    print(f"[ARB_TG] getUpdates статус {resp.status}: {body[:200]}")
                    await asyncio.sleep(5)
                    continue
                data = await resp.json()
        except aiohttp.ClientError as exc:
            print(f"[ARB_TG] Сетевая ошибка getUpdates: {exc}")
            await asyncio.sleep(5)
            continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB_TG] Неожиданная ошибка getUpdates: {exc}")
            await asyncio.sleep(5)
            continue

        if not data.get("ok"):
            print(f"[ARB_TG] Telegram вернул not ok: {data}")
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
                        await answer_callback(session, cb["id"], "\u0414\u043e\u0441\u0442\u0443\u043f \u0437\u0430\u043f\u0440\u0435\u0449\u0451\u043d")
                    except Exception:  # noqa: BLE001
                        pass
                continue

            try:
                if upd.get("callback_query"):
                    await _process_callback(session, state, upd["callback_query"])
                elif upd.get("message"):
                    await _process_message(session, state, upd["message"])
            except Exception as exc:  # noqa: BLE001
                print(f"[ARB_TG] Ошибка обработки апдейта: {exc}")
