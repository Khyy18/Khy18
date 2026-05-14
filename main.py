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
import key_manager
import memory
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

    daily_loss_limit = float(getattr(config, "ARB_DAILY_LOSS_USDT", 0) or 0)
    weekly_loss_limit = float(getattr(config, "ARB_WEEKLY_LOSS_USDT", 0) or 0)

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

    # 1. Мониторинг и закрытие.
    try:
        closed = await arb_executor.monitor_and_maybe_close(
            session, _FUNDING_ADAPTERS, snapshots, _arb_notify(session)
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ARB-EXEC] monitor exception: {exc}")
        closed = False

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

    # 4. Открытие новых, пока есть свободные слоты.
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    slots = max_pos - len(arb_storage.get_all_active())
    for _ in range(max(0, slots)):
        try:
            opened = await arb_executor.evaluate_and_open(
                session, active_adapters, snapshots, _arb_notify(session)
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[ARB-EXEC] open exception: {exc}")
            break
        if not opened:
            break


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
        "💓 <b>Heartbeat</b> — бот жив",
        f"Время: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Executor: {'ON' if executor_on else 'OFF'}  |  Bot: {bot_running}  |  Kill: {ks}",
        f"Funding-snap: {snap_age_str}",
        f"Открытых пар: {active_count}/{max_pos}",
        f"Daily PnL: {daily:+.2f}  |  Weekly: {weekly:+.2f}  |  Total: {cumul:+.2f} USDT",
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
            await _heartbeat_tick(session, state, now)
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] Верхнеуровневая ошибка: {exc}")
        await asyncio.sleep(TICK_SECONDS)


# --- State / startup --------------------------------------------------

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
    state = _build_state()

    async with aiohttp.ClientSession() as session:
        print("[MAIN] Zenith Funding Arbitrage запущен")
        print(f"[MAIN] Биржи в скане: {', '.join(_FUNDING_ADAPTERS.keys()) or '—'}")
        print(
            f"[MAIN] Executor: "
            f"{'ON' if getattr(config, 'ARB_EXECUTOR_ENABLED', False) else 'OFF (read-only)'}"
        )

        await asyncio.gather(
            trading_loop(state, session),
            telegram_bot.run_bot(state, session),
            dashboard.start_server(state),
            return_exceptions=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
