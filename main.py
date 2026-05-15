"""Точка входа Zenith Funding Arbitrage Bot.

Один процесс держит:
  - Funding-сканер: раз в FUNDING_SCAN_INTERVAL_SEC опрашивает все
    публичные funding-эндпоинты бирж из FUNDING_SCAN_EXCHANGES, складывает
    срез в state["global"]["funding_snapshot"].
  - Funding-executor: если ARB_EXECUTOR_ENABLED=1, ищет cross-exchange
    кандидатов (LONG perp на бирже A + SHORT perp на бирже B по тому же
    символу) с net_apr >= ARB_OPEN_MIN_NET_APR, открывает дельта-нейтральные
    пары и закрывает их, когда edge падает ниже ARB_CLOSE_NET_APR или
    срабатывает таймстоп / kill-switch.
  - Telegram-терминал: long-polling, инлайн-меню, ручное управление
    (старт/стоп, паника, ручное закрытие, ротация ключей).
  - Веб-дашборд: read-only HTTP на DASHBOARD_PORT (опционально).

Из репозитория удалены directional-стратегия (Donchian/momentum), AI-роутер,
backtester и всё, что к ним относилось — это funding-only бот.

Принципы:
  - Любая транзиентная ошибка (сеть/биржа/БД) логируется по-русски
    и НЕ валит цикл. Тики идут дальше.
  - kill-switches работают только на funding-уровне: ARB_DAILY_LOSS_USDT,
    ARB_WEEKLY_LOSS_USDT. Отдельного directional MDD нет.
  - Все секреты — из окружения (см. .env.example).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

import arb_executor
import arb_storage
import arbitrage_engine
import config
import dashboard
import funding_history
import key_manager
import lending_advisor
import memory
import rebalancer
import state_persistence
import telegram_bot
from exchanges import get_adapter


TICK_SECONDS = 30


# --- Adapters ---------------------------------------------------------

# Адаптеры всех бирж из FUNDING_SCAN_EXCHANGES создаём по разу на старте.
# Funding-info ходит в публичные эндпоинты, ключи нужны только для
# открытия/закрытия позиций (и проверяются в arb_executor отдельно).
_FUNDING_ADAPTERS: dict[str, Any] = {}
for _ex_name in getattr(config, "FUNDING_SCAN_EXCHANGES", ()):
    try:
        _FUNDING_ADAPTERS[_ex_name] = get_adapter(_ex_name)
    except Exception as _exc:  # noqa: BLE001
        print(f"[ARB] Адаптер {_ex_name} недоступен, пропуск: {_exc}")


def _get_active_adapters(state: dict[str, Any]) -> dict[str, Any]:
    """Только не отключённые пользователем биржи. Отключение через Telegram."""
    disabled: set[str] = set(state.get("global", {}).get("disabled_exchanges") or [])
    if not disabled:
        return _FUNDING_ADAPTERS
    return {k: v for k, v in _FUNDING_ADAPTERS.items() if k not in disabled}


# --- Time helpers -----------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _from_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _floor_utc_midnight(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.astimezone(timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


# --- PnL anchors / kill-switches --------------------------------------

def _roll_daily_weekly_anchors(state: dict[str, Any], now: datetime) -> None:
    """На границе UTC-суток / ISO-недели сбрасываем daily_pnl / weekly_pnl
    арб-движка. cumulative_pnl_arb (за всё время) НЕ сбрасывается."""
    g = state["global"]

    anchor_daily = _from_iso(g.get("daily_anchor_iso"))
    if anchor_daily is None or anchor_daily.date() < now.date():
        if anchor_daily is not None:
            print(
                f"[LOOP] Daily anchor сброшен: arb_daily_pnl={g.get('arb_daily_pnl', 0.0)}"
            )
        g["arb_daily_pnl"] = 0.0
        g["daily_anchor_iso"] = _iso(_floor_utc_midnight(now))

    anchor_weekly = _from_iso(g.get("weekly_anchor_iso"))
    current_week = _iso_week_key(now)
    if anchor_weekly is None or _iso_week_key(anchor_weekly) != current_week:
        if anchor_weekly is not None:
            print(
                f"[LOOP] Weekly anchor сброшен: arb_weekly_pnl={g.get('arb_weekly_pnl', 0.0)}"
            )
        g["arb_weekly_pnl"] = 0.0
        d = now.astimezone(timezone.utc)
        monday = _floor_utc_midnight(d) - timedelta(days=d.weekday())
        g["weekly_anchor_iso"] = _iso(monday)


def _refresh_arb_pnl_from_storage(state: dict[str, Any]) -> None:
    """Пересчитать arb_daily_pnl / arb_weekly_pnl / cumulative из БД.

    Берём все CLOSED записи и фильтруем по closed_ts. Это honest-источник:
    если бот перезапустился, цифры не теряются.
    """
    g = state["global"]
    daily_anchor = _from_iso(g.get("daily_anchor_iso"))
    weekly_anchor = _from_iso(g.get("weekly_anchor_iso"))
    daily_sum = 0.0
    weekly_sum = 0.0
    total_sum = 0.0

    try:
        rows = arb_storage.get_recent_closed(limit=200)
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] _refresh_arb_pnl_from_storage: {exc}")
        return

    for r in rows:
        if r.get("status") != "CLOSED":
            continue
        pnl = float(r.get("pnl_total") or 0.0)
        total_sum += pnl
        ts = _from_iso(r.get("closed_ts"))
        if ts is None:
            continue
        if daily_anchor and ts >= daily_anchor:
            daily_sum += pnl
        if weekly_anchor and ts >= weekly_anchor:
            weekly_sum += pnl

    g["arb_daily_pnl"] = daily_sum
    g["arb_weekly_pnl"] = weekly_sum
    g["arb_cumulative_pnl"] = total_sum
    # Алиасы для UI (telegram_bot/dashboard ожидают эти ключи).
    g["daily_pnl"] = daily_sum
    g["weekly_pnl"] = weekly_sum
    g["cumulative_pnl"] = total_sum


async def _notify(session: aiohttp.ClientSession, text: str) -> None:
    try:
        await telegram_bot.send_message(
            session, text, reply_markup=telegram_bot.set_keyboard()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[NOTIFY] {exc}")


def _arb_notify(session: aiohttp.ClientSession):
    async def _n(text: str) -> None:
        await _notify(session, text)
    return _n


def _format_batch_open(arb_ids: list[int], state: dict[str, Any]) -> str:
    """Сводное уведомление об открытии batch'а арб-связок."""
    active_all = arb_storage.get_all_active()
    active_map = {int(p["id"]): p for p in active_all}
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    lines: list[str] = ["\U0001f4c8 <b>Открыты связки</b>"]
    total_notional = 0.0
    total_edge = 0.0
    count = 0

    for arb_id in arb_ids:
        pos = active_map.get(arb_id)
        if not pos:
            lines.append(f"\n#{arb_id} \u2014 данные недоступны")
            continue
        sym = pos.get("symbol", "-")
        long_ex = pos.get("long_exchange", "-")
        short_ex = pos.get("short_exchange", "-")
        notional = float(pos.get("notional_usdt") or 0)
        edge_apr = float(pos.get("edge_apr_open") or 0)
        tier = pos.get("tier", "?")
        total_notional += notional
        total_edge += edge_apr
        count += 1
        lines.append(f"\n<b>#{arb_id} {sym}</b>")
        lines.append(f"  LONG@{long_ex} | SHORT@{short_ex}")
        lines.append(f"  Notional: ${notional:.0f} (tier_{tier}) | Edge: {edge_apr*100:.1f}% APR")

    # Портфель после открытия
    if count > 0:
        avg_edge = total_edge / count
        # Ожидаемый PnL за 7д (грубая оценка: notional * avg_edge * 7/365)
        expected_7d = total_notional * avg_edge * 7 / 365
        total_active = len(active_all)
        total_not_all = sum(float(p.get("notional_usdt") or 0) for p in active_all)
        lines.append(f"\n<b>Портфель:</b>")
        lines.append(f"  Связок: {total_active}/{max_pos} | Notional: ${total_not_all:.0f}")
        lines.append(f"  Средний edge: {avg_edge*100:.1f}% APR")
        lines.append(f"  Ожидаемый PnL (7д): ~${expected_7d:.2f} USDT")

    return "\n".join(lines)


def _format_batch_close(closed_records: list[dict], state: dict[str, Any]) -> str:
    """Сводное уведомление о закрытии batch'а арб-связок."""
    lines: list[str] = ["\U0001f4c9 <b>Закрыты связки</b>"]
    total_pnl = 0.0
    for r in closed_records:
        arb_id = r.get("id", "?")
        sym = r.get("symbol", "-")
        pnl = float(r.get("pnl_total") or 0.0)
        reason = r.get("close_reason") or "н/д"
        funding = float(r.get("funding_received") or 0.0)
        total_pnl += pnl
        arrow = "\u25b2" if pnl >= 0 else "\u25bc"
        lines.append(f"\n<b>#{arb_id} {sym}</b> {arrow} {pnl:+.4f} USDT")
        lines.append(f"  Причина: {reason}")
        lines.append(f"  Funding получено: {funding:+.4f}")
    lines.append(f"\n<b>Итого PnL:</b> {total_pnl:+.4f} USDT")
    # Оставшиеся позиции
    remaining = arb_storage.get_all_active()
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    lines.append(f"Связок осталось: {len(remaining)}/{max_pos}")
    return "\n".join(lines)


async def _apply_arb_kill_switches(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Killswitch'ы на основе арб-PnL.

    DAILY: если суточный убыток (отрицательный PnL) превысил ARB_DAILY_LOSS_USDT
           - executor выключаем до конца UTC-суток, открытые пары закрываем.
    WEEKLY: то же на недельной шкале, на 7 дней.
    """
    g = state["global"]
    ks_before = g.get("kill_switch_state", "NONE")
    until = _from_iso(g.get("kill_until_utc"))

    # Снятие по истечению.
    if ks_before in ("DAILY", "WEEKLY") and until is not None and now >= until:
        print(f"[KILL] {ks_before} kill-switch снят по расписанию")
        g["kill_switch_state"] = "NONE"
        g["kill_until_utc"] = None
        g["kill_detail"] = ""
        ks_before = "NONE"

    daily_loss_usdt = float(getattr(config, "ARB_DAILY_LOSS_USDT", 0) or 0)
    weekly_loss_usdt = float(getattr(config, "ARB_WEEKLY_LOSS_USDT", 0) or 0)
    daily_loss_pct = float(getattr(config, "ARB_DAILY_LOSS_PCT", 0) or 0)
    weekly_loss_pct = float(getattr(config, "ARB_WEEKLY_LOSS_PCT", 0) or 0)

    # Эффективный лимит = max(USDT, equity*pct). Так бот корректно
    # масштабируется при росте/падении капитала.
    equity_proxy = float(g.get("equity_start") or 0.0)
    if equity_proxy <= 0:
        # Стартовый баланс ещё не получен — fallback на USDT-only.
        daily_loss_limit = daily_loss_usdt
        weekly_loss_limit = weekly_loss_usdt
    else:
        daily_loss_limit = max(daily_loss_usdt, equity_proxy * daily_loss_pct)
        weekly_loss_limit = max(weekly_loss_usdt, equity_proxy * weekly_loss_pct)

    daily_pnl = float(g.get("arb_daily_pnl", 0.0) or 0.0)
    weekly_pnl = float(g.get("arb_weekly_pnl", 0.0) or 0.0)

    if daily_loss_limit > 0 and daily_pnl <= -daily_loss_limit and ks_before == "NONE":
        until_dt = _floor_utc_midnight(now) + timedelta(days=1)
        detail = (
            f"Суточный убыток арб-движка {daily_pnl:.2f} USDT превысил лимит "
            f"−{daily_loss_limit:.2f}. Пауза до {_iso(until_dt)}."
        )
        g["kill_switch_state"] = "DAILY"
        g["kill_until_utc"] = _iso(until_dt)
        g["kill_detail"] = detail
        print(f"[KILL] DAILY активирован: {detail}")
        await _notify(session, "🛑 <b>DAILY kill-switch</b>\n" + detail)
        ks_before = "DAILY"

    if (
        weekly_loss_limit > 0
        and weekly_pnl <= -weekly_loss_limit
        and ks_before in ("NONE", "DAILY")
    ):
        until_dt = now + timedelta(days=7)
        detail = (
            f"Недельный убыток арб-движка {weekly_pnl:.2f} USDT превысил лимит "
            f"−{weekly_loss_limit:.2f}. Пауза до {_iso(until_dt)}."
        )
        g["kill_switch_state"] = "WEEKLY"
        g["kill_until_utc"] = _iso(until_dt)
        g["kill_detail"] = detail
        print(f"[KILL] WEEKLY активирован: {detail}")
        await _notify(session, "🛑 <b>WEEKLY kill-switch</b>\n" + detail)


# --- Tick: funding scan -----------------------------------------------

async def _funding_scan_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Снять funding-снапшот по всем активным биржам.

    Анти-спам алертов: для каждой пары (биржа, символ) после отправки
    запоминается момент - повторный алерт уйдёт не раньше FUNDING_ALERT_COOLDOWN_SEC.
    """
    g = state["global"]
    last_epoch = float(g.get("last_funding_scan_epoch") or 0.0)
    interval = float(getattr(config, "FUNDING_SCAN_INTERVAL_SEC", 300))
    if (time.time() - last_epoch) < interval:
        return

    if not _FUNDING_ADAPTERS:
        g["last_funding_scan_epoch"] = time.time()
        return

    active_adapters = _get_active_adapters(state)
    try:
        snapshots = await arbitrage_engine.scan_funding(session, active_adapters)
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB] Ошибка scan_funding: {exc}")
        g["last_funding_scan_epoch"] = time.time()
        return

    g["funding_snapshot"] = snapshots
    g["last_funding_scan_epoch"] = time.time()

    # Записываем срез в funding_history для anti-spike фильтра.
    try:
        n = funding_history.record_snapshots(snapshots)
        if n > 0:
            print(f"[FUND-HIST] Записано {n} snapshots")
    except Exception as exc:  # noqa: BLE001
        print(f"[FUND-HIST] record fail: {exc}")

    # Anomaly detection на funding-APR. Z-score детектор по
    # (биржа, символ): если текущее значение выпало за threshold σ от
    # своей собственной 100-точечной истории — алерт. Любая ошибка
    # этой секции НЕ должна валить funding_scan_tick.
    try:
        import anomaly_detector
        detector = anomaly_detector.get_detector()
        for ex_name, snaps in snapshots.items():
            for s in snaps:
                metric_name = f"funding_apr_{ex_name}_{s.symbol}"
                alert = detector.record(metric_name, s.apr)
                if alert:
                    await _notify(session, (
                        f"📊 <b>Аномалия в funding</b>\n"
                        f"Метрика: <code>{alert['metric']}</code>\n"
                        f"Значение: {alert['value']:.4f} APR (z={alert['z_score']:.2f}σ)\n"
                        f"Среднее за окно: {alert['mean']:.4f} ± {alert['std']:.4f}"
                    ))
    except Exception as exc:  # noqa: BLE001
        print(f"[ANOMALY-FUNDING] {exc}")

    # Алерты по высокому |net_apr|.
    alert_threshold = float(getattr(config, "FUNDING_ALERT_APR", 0.30))
    cooldown = float(getattr(config, "FUNDING_ALERT_COOLDOWN_SEC", 6 * 3600))
    seen: dict[str, float] = g.get("funding_alert_seen") or {}

    interesting = arbitrage_engine.top_by_apr(
        snapshots, limit=20, min_abs_apr=alert_threshold
    )
    sent = 0
    for snap in interesting:
        key = f"{snap.exchange}:{snap.symbol}"
        last_alert = float(seen.get(key) or 0.0)
        if (time.time() - last_alert) < cooldown:
            continue
        side_label = {
            "SHORT_PERP": "SHORT perp ↘ (получаем funding)",
            "LONG_PERP": "LONG perp ↗ (получаем funding)",
            "FLAT": "нейтрально",
        }.get(snap.side_recommendation, "?")
        text = (
            "📡 <b>Funding-алерт</b>\n"
            f"Биржа: <b>{snap.exchange}</b>  |  Символ: <b>{snap.symbol}</b>\n"
            f"Funding (за {snap.interval_hours:.0f}ч): "
            f"{arbitrage_engine.format_pct(snap.funding_rate)}\n"
            f"APR (брутто): {arbitrage_engine.format_apr(snap.apr)}\n"
            f"APR (net, holding="
            f"{int(getattr(config, 'FUNDING_HOLDING_DAYS', 7))}д): "
            f"<b>{arbitrage_engine.format_apr(snap.net_apr)}</b>\n"
            f"Сторона: {side_label}\n"
            f"Mark: {snap.mark_price:.4f}"
        )
        try:
            await _notify(session, text)
            seen[key] = time.time()
            sent += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB] Ошибка алерта {key}: {exc}")

    g["funding_alert_seen"] = seen
    if sent:
        print(f"[ARB] Funding-алертов отправлено: {sent}")


# --- Tick: arb executor -----------------------------------------------

async def _arb_executor_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Открытие/закрытие/учёт арб-пар."""
    g = state["global"]
    last_epoch = float(g.get("last_arb_exec_epoch") or 0.0)
    interval = float(getattr(config, "ARB_TICK_INTERVAL_SEC", 300))
    if (time.time() - last_epoch) < interval:
        return
    g["last_arb_exec_epoch"] = time.time()

    active_adapters = _get_active_adapters(state)
    if not active_adapters:
        return
    snapshots = g.get("funding_snapshot")
    if not snapshots:
        return

    # Killswitch: forced close всех открытых.
    ks = str(g.get("kill_switch_state") or "NONE")
    if ks != "NONE":
        for active in arb_storage.get_all_active():
            await arb_executor._force_close(
                session, _FUNDING_ADAPTERS, active,
                f"global_kill_switch={ks}",
                _arb_notify(session),
            )
        return

    if not g.get("bot_running", True):
        # Пользователь нажал паузу - новые не открываем, открытые мониторим.
        try:
            await arb_executor.monitor_and_maybe_close(
                session, _FUNDING_ADAPTERS, snapshots, _arb_notify(session)
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] monitor (paused) exception: {exc}")
        return

    # 1. Мониторинг и закрытие (сводное уведомление).
    active_before = set(p["id"] for p in arb_storage.get_all_active())
    try:
        closed = await arb_executor.monitor_and_maybe_close(
            session, _FUNDING_ADAPTERS, snapshots, _arb_notify(session)
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] monitor exception: {exc}")
        closed = False

    if closed:
        # Определяем какие пары были закрыты
        active_after = set(p["id"] for p in arb_storage.get_all_active())
        closed_ids = active_before - active_after
        if closed_ids:
            try:
                recent = arb_storage.get_recent_closed(limit=len(closed_ids) + 2)
                closed_records = [r for r in recent if r.get("id") in closed_ids]
                if closed_records:
                    text = _format_batch_close(closed_records, state)
                    await _notify(session, text)
            except Exception as exc:  # noqa: BLE001
                print(f"[ARB-EXEC] batch_close notify error: {exc}")

    # 2. Учёт funding-выплат.
    try:
        await arb_executor.reconcile_funding_payments(
            session, _FUNDING_ADAPTERS, snapshots
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] reconcile_funding exception: {exc}")

    # 3. После закрытия — пересканируем сразу, чтобы не открыть на устаревших данных.
    if closed:
        try:
            fresh = await arbitrage_engine.scan_funding(session, active_adapters)
            snapshots = fresh
            g["funding_snapshot"] = fresh
            g["last_funding_scan_epoch"] = time.time()
            print("[ARB-EXEC] Ресканинг после закрытия")
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] Ресканинг не удался: {exc}")
            return

    # 4. Открытие новых, пока есть свободные слоты (batch-уведомление).
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    slots = max_pos - len(arb_storage.get_all_active())
    opened_ids: list[int] = []
    for _ in range(max(0, slots)):
        try:
            opened = await arb_executor.evaluate_and_open(
                session, active_adapters, snapshots, notify=None,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] open exception: {exc}")
            break
        if not opened:
            break
        opened_ids.append(opened)

    # Сводное уведомление по batch'у открытий.
    if opened_ids:
        text = _format_batch_open(opened_ids, state)
        await _notify(session, text)


# --- Tick: anomaly detection ------------------------------------------

async def _anomaly_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Раз в 10 минут проверяем подозрительные паттерны и шлём warn в Telegram.

    Срабатывает если:
      - executor включён, но >24ч не было ни одного открытия;
      - circuit breaker какой-то биржи сидит в OPEN > 30 минут;
      - всех бирж в скане 0 (катастрофа).

    Анти-спам: каждый тип алерта посылается не чаще раз в 4 часа.
    """
    g = state["global"]
    last_check = float(g.get("last_anomaly_check_epoch") or 0.0)
    interval = 600.0  # 10 минут
    if (time.time() - last_check) < interval:
        return
    g["last_anomaly_check_epoch"] = time.time()

    seen: dict[str, float] = g.get("anomaly_alert_seen") or {}
    cooldown = 4 * 3600.0

    def _send_once(key: str) -> bool:
        last = float(seen.get(key) or 0.0)
        if (time.time() - last) < cooldown:
            return False
        seen[key] = time.time()
        return True

    # 1. Executor on, но 24ч без открытий.
    if getattr(config, "ARB_EXECUTOR_ENABLED", False):
        try:
            recent = arb_storage.get_recent_closed(limit=50) or []
            active = arb_storage.get_all_active() or []
            last_open_ts = 0.0
            for r in recent + active:
                ts_str = r.get("opened_ts") or ""
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(str(ts_str))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        last_open_ts = max(last_open_ts, ts.timestamp())
                    except Exception:  # noqa: BLE001
                        pass
            if last_open_ts > 0:
                age_h = (time.time() - last_open_ts) / 3600.0
                if age_h > 24.0 and _send_once("no_opens_24h"):
                    await _notify(session, (
                        "⚠️ <b>Аномалия:</b> executor включён, "
                        f"но {age_h:.0f}ч без открытий.\n"
                        "Пороги ARB_OPEN_MIN_NET_APR слишком высокие или рынок без edge."
                    ))
        except Exception as exc:  # noqa: BLE001
            print(f"[ANOMALY] no-opens check fail: {exc}")

    # 2. Circuit breaker долго в OPEN.
    try:
        import circuit_breaker as cb_mod
        snap = cb_mod.get_breaker().status_snapshot()
        for ex_name, st in snap.items():
            if st.get("state") == "OPEN":
                remaining = int(st.get("cooldown_remaining_sec") or 0)
                if _send_once(f"breaker_open_{ex_name}"):
                    await _notify(session, (
                        f"⚠️ <b>Биржа {ex_name} недоступна</b>\n"
                        f"Circuit breaker OPEN, cooldown ~{remaining // 60}мин.\n"
                        f"Last error: <code>{st.get('last_failure_msg', '')[:100]}</code>"
                    ))
    except Exception as exc:  # noqa: BLE001
        print(f"[ANOMALY] breaker check fail: {exc}")

    # 3. Все адаптеры пусты.
    active = _get_active_adapters(state)
    if not active and _send_once("no_adapters"):
        await _notify(session, (
            "🚨 <b>Критично:</b> ни одной биржи в скане. "
            "Проверьте FUNDING_SCAN_EXCHANGES и disabled_exchanges."
        ))

    g["anomaly_alert_seen"] = seen


# --- Tick: periodic position check (orphaned leg detection) -----------

async def _position_check_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Раз в POSITION_CHECK_INTERVAL_SEC (default 600 = 10мин) проверяем
    что позиции на биржах совпадают с записями в БД.

    Если обнаруживаем что нога пропала (ликвидация / manual close на бирже):
      - force_close оставшуюся ногу
      - mark_failed с причиной "orphaned_leg_detected"
      - алерт в Telegram
    """
    g = state["global"]
    last = float(g.get("last_position_check_epoch") or 0)
    interval = float(getattr(config, "POSITION_CHECK_INTERVAL_SEC", 600))
    if (time.time() - last) < interval:
        return
    g["last_position_check_epoch"] = time.time()

    positions = arb_storage.get_all_active()
    if not positions:
        return

    for pos in positions:
        if pos.get("status") != "OPEN":
            continue
        sym = pos["symbol"]
        long_ex = pos["long_exchange"]
        short_ex = pos["short_exchange"]
        arb_id = int(pos["id"])
        qty = float(pos.get("qty_base") or 0)
        if qty <= 0:
            continue

        # Проверяем каждую ногу.
        for ex_name, side_label in [(long_ex, "LONG"), (short_ex, "SHORT")]:
            adapter = _FUNDING_ADAPTERS.get(ex_name)
            if not adapter:
                continue
            try:
                exchange_positions = await adapter.get_positions(session, sym)
            except Exception as exc:  # noqa: BLE001
                print(f"[POS-CHECK] {ex_name}/{sym}: get_positions fail: {exc}")
                continue

            # Считаем что позиция есть, если хотя бы одна запись с size > 0.
            has_position = False
            for ep in (exchange_positions or []):
                try:
                    size = float(ep.get("size") or ep.get("qty") or 0)
                except (TypeError, ValueError):
                    size = 0.0
                if size > 0:
                    has_position = True
                    break

            if not has_position:
                # ORPHANED LEG DETECTED!
                print(f"[POS-CHECK] ORPHAN: #{arb_id} {sym} — {side_label}@{ex_name} пропала!")

                # Закрываем оставшуюся ногу.
                other_ex = short_ex if ex_name == long_ex else long_ex
                other_adapter = _FUNDING_ADAPTERS.get(other_ex)
                if other_adapter:
                    other_side = "Buy" if ex_name == long_ex else "Sell"  # close opposite
                    try:
                        await arb_executor._close_leg(
                            session, other_adapter, sym, other_side, qty,
                            f"ORPHAN-CLOSE {side_label}@{other_ex}",
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"[POS-CHECK] orphan close fail: {exc}")

                arb_storage.mark_failed(arb_id, f"orphaned_leg_{side_label}@{ex_name}_missing")

                await _notify(session, (
                    f"🚨 <b>Orphaned leg!</b>\n\n"
                    f"Связка #{arb_id} {sym}:\n"
                    f"{side_label}@{ex_name} — позиция ПРОПАЛА (ликвидация?)\n"
                    f"Вторая нога закрыта reduce-only.\n\n"
                    f"Проверьте биржу {ex_name} вручную!"
                ))
                break  # не проверяем вторую ногу — уже пометили FAILED


# --- Tick: rebalancer (advisor) ---------------------------------------

async def _rebalance_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Сверка USDT-балансов между биржами и рекомендация ручных переводов.

    Работает раз в REBALANCE_CHECK_INTERVAL_SEC. Реальные withdraw'ы НЕ
    делает — только присылает в Telegram список "переведи X с биржи A
    на биржу B". Это сознательное MVP-решение: автоматический withdraw
    слишком опасен.
    """
    g = state["global"]
    last_epoch = float(g.get("last_rebalance_check_epoch") or 0.0)
    interval = float(getattr(config, "REBALANCE_CHECK_INTERVAL_SEC", 3600))
    if (time.time() - last_epoch) < interval:
        return
    g["last_rebalance_check_epoch"] = time.time()

    active_adapters = _get_active_adapters(state)
    if len(active_adapters) < 2:
        # Минимум 2 биржи нужно для перевода.
        return

    # Cooldown-словарь храним прямо в global, чтобы переживал перезапуск
    # секций кода (но не процесса — это OK, в худшем случае один лишний
    # алерт после рестарта).
    if "rebalance_alert_seen" not in g:
        g["rebalance_alert_seen"] = {}

    # rebalancer.check_and_alert ожидает state как dict с ключом
    # rebalance_alert_seen на верхнем уровне. Передаём g (то есть
    # state["global"]) — там и лежит этот ключ.
    try:
        await rebalancer.check_and_alert(
            session, active_adapters, _arb_notify(session), g,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[REBAL] tick exception: {exc}")


# --- Tick: lending advisor --------------------------------------------

async def _lending_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Сверка простаивающего USDT на биржах и рекомендация подписать в Earn.

    Работает раз в LENDING_CHECK_INTERVAL_SEC (default 6ч). Реальных
    подписок не делает — только присылает в Telegram список "сколько
    USDT подписать в Earn flex на каждой бирже".

    Логика расчёта см. lending_advisor.check_idle_balances():
      idle = free_usdt - margin_in_use - reserve.

    margin_in_use берётся из активных арб-пар (notional / leverage).
    Резерв — max(LENDING_RESERVE_PCT * balance, LENDING_MIN_RESERVE_USDT).
    """
    g = state["global"]
    last_epoch = float(g.get("last_lending_check_epoch") or 0.0)
    interval = float(getattr(config, "LENDING_CHECK_INTERVAL_SEC", 6 * 3600.0))
    if (time.time() - last_epoch) < interval:
        return
    g["last_lending_check_epoch"] = time.time()

    active_adapters = _get_active_adapters(state)
    if not active_adapters:
        return

    if "lending_alert_seen" not in g:
        g["lending_alert_seen"] = {}

    try:
        await lending_advisor.check_idle_balances(
            session, active_adapters, _arb_notify(session), g,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LEND] tick exception: {exc}")


# --- Tick: announcements ---------------------------------------------

async def _announcement_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Опросить announcement-эндпоинты бирж и обновить blacklist.

    Работает раз в ANNOUNCE_CHECK_INTERVAL_SEC (default 1ч). Реальной
    торговли не делает — только классифицирует анонсы и шлёт алерт +
    обновляет state["global"]["announcement_blacklist"]. Если хоть
    одна нога будущего кандидата в evaluate_and_open попадёт в этот
    blacklist, кандидат будет пропущен.
    """
    g = state["global"]
    last = float(g.get("last_announcement_check_epoch") or 0.0)
    interval = float(getattr(config, "ANNOUNCE_CHECK_INTERVAL_SEC", 3600))
    if (time.time() - last) < interval:
        return
    g["last_announcement_check_epoch"] = time.time()

    active_adapters = _get_active_adapters(state)
    if not active_adapters:
        return

    try:
        import announcement_monitor
        await announcement_monitor.check_and_alert(
            session, active_adapters, _arb_notify(session), g,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ANNOUNCE] tick fail: {exc}")


# --- Tick: heartbeat --------------------------------------------------

async def _heartbeat_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    g = state["global"]
    last_epoch = float(g.get("last_heartbeat_epoch") or 0.0)
    interval = float(getattr(config, "HEARTBEAT_INTERVAL_SEC", 6 * 3600))
    if (time.time() - last_epoch) < interval:
        return

    active_count = len(arb_storage.get_all_active())
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    daily = float(g.get("arb_daily_pnl", 0.0) or 0.0)
    weekly = float(g.get("arb_weekly_pnl", 0.0) or 0.0)
    cumul = float(g.get("arb_cumulative_pnl", 0.0) or 0.0)
    ks = str(g.get("kill_switch_state") or "NONE")
    bot_running = "ON" if g.get("bot_running") else "PAUSED"
    executor_on = bool(getattr(config, "ARB_EXECUTOR_ENABLED", False))
    snap_age = (
        time.time() - float(g.get("last_funding_scan_epoch") or 0.0)
        if g.get("last_funding_scan_epoch") else None
    )
    snap_age_str = f"{int(snap_age)}с назад" if snap_age is not None else "ещё не было"

    parts = [
        "\U0001f493 <b>Heartbeat</b>",
        telegram_bot._DIVIDER,
        f"<pre>Время: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Executor: {'ON' if executor_on else 'OFF'}  |  Bot: {bot_running}  |  Kill: {ks}",
        f"Funding-snap: {snap_age_str}",
        f"Связок: {active_count}/{max_pos}",
        f"Daily PnL: {daily:+.2f}  |  Weekly: {weekly:+.2f}",
        f"Total: {cumul:+.2f} USDT</pre>",
    ]

    try:
        await _notify(session, "\n".join(parts))
        print("[HB] Отправлено")
    except Exception as exc:  # noqa: BLE001
        print(f"[HB] Ошибка: {exc}")
    g["last_heartbeat_epoch"] = time.time()


# --- Main loop --------------------------------------------------------

async def trading_loop(
    state: dict[str, Any],
    session: aiohttp.ClientSession,
) -> None:
    """Главный цикл: на каждом тике крутим funding-scan, executor, kill-switches,
    heartbeat и сводку. Все ошибки ловим внутри тиков, общий цикл не падает."""
    print("[LOOP] Funding-arbitrage loop запущен")
    while True:
        now = _utc_now()
        try:
            _roll_daily_weekly_anchors(state, now)
            _refresh_arb_pnl_from_storage(state)
            await _apply_arb_kill_switches(session, state, now)

            await _funding_scan_tick(session, state, now)
            await _arb_executor_tick(session, state, now)
            await _anomaly_tick(session, state, now)
            await _position_check_tick(session, state, now)
            await _rebalance_tick(session, state, now)
            await _lending_tick(session, state, now)
            await _announcement_tick(session, state, now)
            await _heartbeat_tick(session, state, now)

            # State persistence: сохраняем раз в STATE_PERSIST_INTERVAL_SEC.
            g = state["global"]
            if (time.time() - g.get("last_persist_epoch", 0)) > 60:
                state_persistence.persist(state)
                g["last_persist_epoch"] = time.time()
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] Верхнеуровневая ошибка: {exc}")
        await asyncio.sleep(TICK_SECONDS)


# --- State / startup --------------------------------------------------

async def _reconcile_arb_positions(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Сверка локальной БД активных арб-пар с реальными позициями на биржах.

    Вызывается ОДИН раз на старте бота, перед запуском trading_loop.
    Проверяем для каждой OPEN/CLOSING пары:
      - LONG-нога присутствует на long_exchange со стороной Buy
      - SHORT-нога присутствует на short_exchange со стороной Sell
      - размер qty совпадает с qty_base из БД (допуск 1%)

    Если позиция в БД есть, а на бирже её НЕТ — отмечаем mark_failed
    с reason 'position_missing_on_exchange:{ex}' и шлём алерт.
    Если qty не совпало — алерт-warning, без mark_failed (могла быть
    частичная заливка или закрытие в обход бота).

    Ошибки сети/адаптера ловим, не валим запуск бота. Если адаптер
    биржи отсутствует (например, не настроен ключ) — пропускаем такую
    пару с предупреждением в лог.
    """
    try:
        active = arb_storage.get_all_active() or []
    except Exception as exc:  # noqa: BLE001
        print(f"[RECONCILE] arb_storage.get_all_active fail: {exc}")
        return

    if not active:
        print("[RECONCILE] Активных пар в БД нет, сверка не нужна")
        return

    print(f"[RECONCILE] Сверяем {len(active)} активных пар с биржами")
    ok_count = 0
    missing_count = 0
    mismatch_count = 0
    qty_tolerance = 0.01  # 1%

    for pos in active:
        try:
            arb_id = int(pos.get("id") or 0)
            symbol = str(pos.get("symbol") or "")
            qty_db = float(pos.get("qty_base") or 0.0)
            long_ex = str(pos.get("long_exchange") or "").lower()
            short_ex = str(pos.get("short_exchange") or "").lower()
        except (TypeError, ValueError) as exc:
            print(f"[RECONCILE] невалидная запись: {exc}, skip")
            continue

        # Каждую ногу сверяем независимо. Если хоть одна не нашлась —
        # пара считается рассинхронизированной.
        for leg_label, ex_name, expected_side in (
            ("LONG", long_ex, "Buy"),
            ("SHORT", short_ex, "Sell"),
        ):
            adapter = _FUNDING_ADAPTERS.get(ex_name)
            if adapter is None:
                print(
                    f"[RECONCILE] arb#{arb_id} {symbol} {leg_label}@{ex_name}: "
                    f"адаптер не настроен, пропуск"
                )
                continue

            try:
                positions_on_ex = await adapter.get_positions(session, symbol)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[RECONCILE] arb#{arb_id} {symbol} {leg_label}@{ex_name}: "
                    f"get_positions fail: {exc}"
                )
                continue

            # Ищем ногу нужной стороны (Buy для LONG, Sell для SHORT).
            matched = None
            for p in positions_on_ex or []:
                if str(p.get("side") or "") == expected_side:
                    try:
                        size = float(p.get("size") or 0.0)
                    except (TypeError, ValueError):
                        size = 0.0
                    if size > 0:
                        matched = p
                        break

            if matched is None:
                missing_count += 1
                reason = f"position_missing_on_exchange:{ex_name}"
                print(
                    f"[RECONCILE] arb#{arb_id} {symbol} {leg_label}@{ex_name}: "
                    f"позиции на бирже НЕТ — mark_failed"
                )
                try:
                    arb_storage.mark_failed(arb_id, reason)
                except Exception as exc:  # noqa: BLE001
                    print(f"[RECONCILE] mark_failed fail: {exc}")
                try:
                    await telegram_bot.send_message(
                        session,
                        (
                            f"🚨 <b>RECONCILE</b> arb#{arb_id} {symbol}\n"
                            f"{leg_label}@{ex_name}: позиции на бирже не найдено.\n"
                            f"Помечаю в БД как FAILED ({reason}). "
                            f"Проверьте вручную."
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[RECONCILE] telegram alert fail: {exc}")
                # Дальше эту пару не проверяем — уже FAILED.
                break

            # Нога есть — сверяем qty.
            try:
                size = float(matched.get("size") or 0.0)
            except (TypeError, ValueError):
                size = 0.0
            if qty_db > 0 and size > 0:
                diff = abs(size - qty_db) / qty_db
                if diff > qty_tolerance:
                    mismatch_count += 1
                    msg = (
                        f"arb#{arb_id} {symbol} {leg_label}@{ex_name}: "
                        f"qty mismatch БД={qty_db} биржа={size} "
                        f"(diff={diff*100:.2f}%)"
                    )
                    print(f"[RECONCILE] WARNING {msg}")
                    try:
                        await telegram_bot.send_message(
                            session,
                            (
                                f"⚠️ <b>RECONCILE warning</b>\n{msg}\n"
                                f"Возможен частичный fill или внеплановое закрытие."
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"[RECONCILE] telegram warn fail: {exc}")
                else:
                    ok_count += 1
            else:
                ok_count += 1

    print(
        f"[RECONCILE] Готово: OK ног={ok_count}, missing={missing_count}, "
        f"qty-mismatch={mismatch_count}"
    )


def _build_state() -> dict[str, Any]:
    return {
        # symbols: пустой словарь. Funding-only бот не торгует по символам
        # как directional, но dashboard/TG обращаются к state["symbols"]
        # через .get() — оставляем для совместимости.
        "symbols": {},
        "global": {
            "bot_running": True,
            "kill_switch_state": "NONE",
            "kill_until_utc": None,
            "kill_detail": "",
            # PnL арб-движка. Дублируем под алиасы, которые читают
            # telegram_bot и dashboard (ожидают daily_pnl / weekly_pnl
            # / cumulative_pnl на верхнем уровне).
            "arb_daily_pnl": 0.0,
            "arb_weekly_pnl": 0.0,
            "arb_cumulative_pnl": 0.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "cumulative_pnl": 0.0,
            "equity_start": None,
            "hwm": 0.0,
            "daily_anchor_iso": None,
            "weekly_anchor_iso": None,
            # Funding scanner.
            "funding_snapshot": None,
            "last_funding_scan_epoch": 0.0,
            "funding_alert_seen": {},
            # Executor.
            "last_arb_exec_epoch": 0.0,
            # Heartbeat.
            "last_heartbeat_epoch": 0.0,
            # Rebalancer (advisor).
            "last_rebalance_check_epoch": 0.0,
            "rebalance_alert_seen": {},
            # Lending advisor.
            "last_lending_check_epoch": 0.0,
            "lending_alert_seen": {},
            # Announcement monitor.
            "last_announcement_check_epoch": 0.0,
            "seen_announcements": [],
            "announcement_blacklist": {},
            # Disabled exchanges (toggle через TG).
            "disabled_exchanges": set(),
            # Legacy-флаги для совместимости с UI.
            "degraded": False,
            "degraded_reason": "",
            "blackout": {"blackout": False, "until_utc": None, "reason": "", "ts": None},
        },
    }


async def main() -> None:
    key_manager.load_overrides()
    missing = config.validate_config()
    if missing:
        print("[MAIN] Отсутствуют переменные окружения: " + ", ".join(missing))
        print("[MAIN] См. .env.example")
        return

    memory.init_db()
    arb_storage.init_arb_db()
    funding_history.init_db()
    state = _build_state()

    # State persistence: инициализация БД и восстановление сохранённого состояния.
    state_persistence.init_db()
    saved = state_persistence.load()
    if saved:
        state_persistence.merge_into_state(state, saved)
        print(f"[STATE] Восстановлено состояние из БД ({len(saved)} ключей)")
    state_persistence.setup_graceful_shutdown(state)

    # Регистрируем state в singleton'е, чтобы модули типа
    # announcement_monitor могли читать blacklist из evaluate_and_open
    # без изменения сигнатур.
    try:
        import runtime_state
        runtime_state.set_state(state)
    except Exception as exc:  # noqa: BLE001
        print(f"[MAIN] runtime_state.set_state fail (не критично): {exc}")

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(
            limit=50,               # max total connections
            limit_per_host=10,      # max per-host (per-exchange)
            ttl_dns_cache=300,      # DNS кэш 5мин
            enable_cleanup_closed=True,
        ),
        timeout=aiohttp.ClientTimeout(
            total=20,       # общий лимит на запрос
            connect=5,      # TCP connect
            sock_read=15,   # ожидание ответа
        ),
    ) as session:
        print("[MAIN] Zenith Funding Arbitrage запущен")
        print(f"[MAIN] Биржи в скане: {', '.join(_FUNDING_ADAPTERS.keys()) or '—'}")
        print(
            f"[MAIN] Executor: "
            f"{'ON' if getattr(config, 'ARB_EXECUTOR_ENABLED', False) else 'OFF (read-only)'}"
        )

        # Сверка локальной БД и реальных позиций на биржах. Делается ОДИН
        # раз перед стартом trading_loop, чтобы не оставить ноги без
        # управления, если SQLite потерялась/разошлась с биржей.
        try:
            await _reconcile_arb_positions(session, state)
        except Exception as exc:  # noqa: BLE001
            print(f"[RECONCILE] Верхнеуровневая ошибка, игнорируем: {exc}")

        await asyncio.gather(
            trading_loop(state, session),
            telegram_bot.run_bot(state, session),
            dashboard.start_server(state),
            return_exceptions=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
