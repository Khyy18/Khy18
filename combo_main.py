"""Точка входа КОМБО-бота: funding-арб + grid + momentum.

Один процесс, один Telegram, три стратегии параллельно.
asyncio event loop с тиками каждой стратегии.

Архитектура:
  - Funding-арб: оригинальный движок из main.py (scan + executor).
  - Grid: grid_engine.grid_tick() раз в GRID_REBALANCE_INTERVAL_SEC.
  - Momentum: momentum_engine.momentum_tick() раз в MOMENTUM_TICK_INTERVAL_SEC.
  - Telegram: combo_telegram.polling_loop() — long polling.
  - Global kill-switch: проверяется каждый тик.

Принципы:
  - Любая ошибка логируется и НЕ валит цикл.
  - Kill-switch останавливает ВСЕ стратегии.
  - State сохраняется на диск через state_persistence.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

import capital_allocator
import combo_config as cfg
import combo_telegram
import config
import global_kill_switch
import grid_engine
import momentum_engine
import state_persistence


# Опциональный импорт funding-модулей (могут быть не нужны, если funding выкл)
try:
    import arb_executor
    import arb_storage
    import arbitrage_engine
    from exchanges import get_adapter

    _FUNDING_AVAILABLE = True
except ImportError as _exc:
    print(f"[COMBO] Funding-модули недоступны: {_exc}")
    _FUNDING_AVAILABLE = False


MAIN_TICK_SECONDS = 30


# ─── State initialization ─────────────────────────────────────────────

def _init_state() -> dict[str, Any]:
    """Создать или восстановить state из persistence."""
    # Пытаемся загрузить из файла
    try:
        state = state_persistence.load_state()
        if state:
            print("[COMBO] State загружен из persistence")
        else:
            state = {}
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO] Не удалось загрузить state: {exc}")
        state = {}

    # Инициализируем все секции
    state.setdefault("global", {})
    g = state["global"]
    g.setdefault("bot_running", True)
    g.setdefault("started_epoch", time.time())

    # Аллокатор капитала
    capital_allocator.init_allocator_state(state)

    # Grid
    grid_engine.init_grid_state(state)

    # Momentum
    momentum_engine.init_momentum_state(state)

    return state


# ─── Funding ticks (делегируем в оригинальный main) ────────────────────

_FUNDING_ADAPTERS: dict[str, Any] = {}


def _init_funding_adapters() -> None:
    """Инициализация funding-адаптеров."""
    if not _FUNDING_AVAILABLE:
        return
    for ex_name in getattr(config, "FUNDING_SCAN_EXCHANGES", ()):
        try:
            _FUNDING_ADAPTERS[ex_name] = get_adapter(ex_name)
        except Exception as exc:  # noqa: BLE001
            print(f"[COMBO] Funding-адаптер {ex_name} недоступен: {exc}")


async def _funding_scan_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Funding-скан (упрощённая версия из main.py)."""
    if not _FUNDING_AVAILABLE or not _FUNDING_ADAPTERS:
        return

    g = state["global"]
    last_epoch = float(g.get("last_funding_scan_epoch") or 0.0)
    interval = float(getattr(config, "FUNDING_SCAN_INTERVAL_SEC", 300))
    if (time.time() - last_epoch) < interval:
        return

    try:
        snapshots = await arbitrage_engine.scan_funding(session, _FUNDING_ADAPTERS)
        g["funding_snapshot"] = snapshots
        g["last_funding_scan_epoch"] = time.time()
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO] funding_scan error: {exc}")
        g["last_funding_scan_epoch"] = time.time()


async def _funding_executor_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Funding-executor (открытие/закрытие пар)."""
    if not _FUNDING_AVAILABLE or not _FUNDING_ADAPTERS:
        return
    if not getattr(config, "ARB_EXECUTOR_ENABLED", False):
        return

    g = state["global"]
    last_epoch = float(g.get("last_arb_exec_epoch") or 0.0)
    interval = float(getattr(config, "ARB_TICK_INTERVAL_SEC", 300))
    if (time.time() - last_epoch) < interval:
        return
    g["last_arb_exec_epoch"] = time.time()

    # Kill-switch — force close всех
    if global_kill_switch.is_kill_active(state):
        try:
            for active in arb_storage.get_all_active():
                await arb_executor._force_close(
                    session, _FUNDING_ADAPTERS, active, "global_combo_kill", None
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[COMBO] funding force_close error: {exc}")
        return

    if not g.get("bot_running", True):
        return

    snapshots = g.get("funding_snapshot")
    if not snapshots:
        return

    # Мониторинг и закрытие
    try:
        closed = await arb_executor.monitor_and_maybe_close(
            session, _FUNDING_ADAPTERS, snapshots, None
        )
        # #3: Sync funding PnL в capital_allocator
        if closed:
            try:
                recent = arb_storage.get_recent_closed(limit=5)
                for r in recent:
                    pnl = float(r.get("pnl_total") or 0.0)
                    if pnl != 0 and r.get("_synced_combo") is None:
                        capital_allocator.record_pnl(state, "funding", pnl)
                        r["_synced_combo"] = True
            except Exception as exc:  # noqa: BLE001
                print(f"[COMBO] funding pnl sync: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO] arb monitor error: {exc}")

    # Открытие новых
    max_pos = int(getattr(config, "ARB_MAX_POSITIONS", 3))
    try:
        slots = max_pos - len(arb_storage.get_all_active())
        for _ in range(max(0, slots)):
            opened = await arb_executor.evaluate_and_open(
                session, _FUNDING_ADAPTERS, snapshots, notify=None
            )
            if not opened:
                break
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO] arb open error: {exc}")


# ─── Persist tick ──────────────────────────────────────────────────────

_last_persist_epoch: float = 0.0


async def _persist_tick(state: dict[str, Any]) -> None:
    """Сохранить state на диск."""
    global _last_persist_epoch
    interval = float(getattr(config, "STATE_PERSIST_INTERVAL_SEC", 60))
    now = time.time()
    if (now - _last_persist_epoch) < interval:
        return
    _last_persist_epoch = now
    try:
        state_persistence.save_state(state)
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO] persist error: {exc}")


# ─── Notify helper ────────────────────────────────────────────────────

async def _notify(session: aiohttp.ClientSession, text: str) -> None:
    """Отправить уведомление в Telegram."""
    try:
        await combo_telegram.send_message(
            session, text, reply_markup=combo_telegram.combo_keyboard()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[COMBO] notify error: {exc}")


# ─── Main loop ─────────────────────────────────────────────────────────

async def _main_loop(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Основной цикл: тики всех стратегий + kill-switch проверка."""
    print("[COMBO] Main loop запущен")

    while True:
        tick_start = time.time()

        try:
            # 1. Проверяем global kill-switch
            was_active = global_kill_switch.is_kill_active(state)
            triggered = global_kill_switch.check_global_kill(state)

            if triggered and not was_active:
                # Только что сработал — уведомляем
                reason = global_kill_switch.get_kill_reason(state)
                await _notify(
                    session,
                    combo_telegram._card(
                        "GLOBAL KILL-SWITCH",
                        "\U0001f6a8",
                        [reason, "", "Все стратегии остановлены."],
                    ),
                )
                # Стопим всё
                try:
                    await grid_engine.stop_grid(session, state)
                except Exception as exc:  # noqa: BLE001
                    print(f"[COMBO] grid stop on kill: {exc}")
                try:
                    await momentum_engine.stop_momentum(session, state)
                except Exception as exc:  # noqa: BLE001
                    print(f"[COMBO] momentum stop on kill: {exc}")

            # 2. Funding-тики (только если kill не активен)
            if not global_kill_switch.is_kill_active(state):
                await _funding_scan_tick(session, state)
                await _funding_executor_tick(session, state)

            # 2.5. AI Regime routing (раз в 5 мин)
            try:
                import ai_integration
                grid_adapter = grid_engine._get_adapter()
                regime_result = await ai_integration.apply_regime_routing(
                    session, state, grid_adapter
                )
                if regime_result.get("regime"):
                    # Логируем смену режима
                    prev_regime = state.get("global", {}).get("_prev_regime", "")
                    new_regime = regime_result["regime"]
                    if new_regime != prev_regime:
                        state["global"]["_prev_regime"] = new_regime
                        await _notify(session, combo_telegram._card(
                            "Режим рынка", "\U0001f9e0", [
                                f"Новый режим: {new_regime}",
                                f"ADX: {regime_result.get('adx', 0):.1f}",
                                f"Confidence: {regime_result.get('confidence', 0):.0%}",
                            ]
                        ))
            except Exception as exc:  # noqa: BLE001
                print(f"[COMBO] regime routing: {exc}")

            # 3. Grid-тик
            try:
                grid_result = await grid_engine.grid_tick(session, state)
                if grid_result.get("errors"):
                    for err in grid_result["errors"]:
                        print(f"[COMBO] grid error: {err}")
                # Нотификации о завершённых циклах grid
                processed = grid_result.get("processed", [])
                for msg in processed:
                    if "циклов завершено" in msg:
                        await _notify(session, combo_telegram._card(
                            "Grid", "\u25a6", [msg]
                        ))
            except Exception as exc:  # noqa: BLE001
                print(f"[COMBO] grid_tick exception: {exc}")

            # 4. Momentum-тик
            try:
                mom_result = await momentum_engine.momentum_tick(session, state)
                if mom_result.get("errors"):
                    for err in mom_result["errors"]:
                        print(f"[COMBO] momentum error: {err}")
                # Нотификации об открытии/закрытии momentum
                processed = mom_result.get("processed", [])
                for msg in processed:
                    if "ОТКРЫТО" in msg or "ЗАКРЫТО" in msg:
                        await _notify(session, combo_telegram._card(
                            "Momentum", "\U0001f4c8", [msg]
                        ))
            except Exception as exc:  # noqa: BLE001
                print(f"[COMBO] momentum_tick exception: {exc}")

            # 5. Обновляем HWM
            capital_allocator.update_hwm(state)

            # 6. Persist state
            await _persist_tick(state)

            # #9: Heartbeat в Telegram (раз в HEARTBEAT_INTERVAL_SEC)
            g = state.get("global", {})
            last_hb = float(g.get("last_heartbeat_epoch", 0))
            if (time.time() - last_hb) >= cfg.HEARTBEAT_INTERVAL_SEC:
                g["last_heartbeat_epoch"] = time.time()
                summary = capital_allocator.get_allocation_summary(state)
                dd = summary["drawdown_pct"]
                eq = summary["current_equity"]
                await _notify(session, combo_telegram._card(
                    "Heartbeat", "\U0001f49a", [
                        f"Equity: ${eq:.2f}  |  DD: {dd*100:.1f}%",
                        f"Grid cycles: {state.get('grid', {}).get('total_cycles', 0)}",
                        f"Mom trades: {state.get('momentum', {}).get('total_trades', 0)}",
                    ]
                ))

            # #7: Сброс daily PnL counters на границе UTC-суток
            from datetime import datetime, timezone
            now_dt = datetime.now(tz=timezone.utc)
            last_day = g.get("_daily_reset_day", "")
            today = now_dt.strftime("%Y-%m-%d")
            if today != last_day:
                g["_daily_reset_day"] = today
                g["daily_pnl_grid"] = 0.0
                g["daily_pnl_momentum"] = 0.0
                g["daily_pnl_funding"] = 0.0

        except Exception as exc:  # noqa: BLE001
            print(f"[COMBO] main_loop tick exception: {exc}")

        # Пауза до следующего тика
        elapsed = time.time() - tick_start
        sleep_time = max(1.0, MAIN_TICK_SECONDS - elapsed)
        await asyncio.sleep(sleep_time)


# ─── Entry point ───────────────────────────────────────────────────────

async def main() -> None:
    """Точка входа: запускает Telegram polling + main loop."""
    # Валидация конфига
    errors = cfg.validate_combo_config()
    if errors:
        print("[COMBO] Ошибки конфигурации:")
        for err in errors:
            print(f"  - {err}")
        print("[COMBO] Запуск с ошибками — проверьте .env")

    # Инициализация
    state = _init_state()
    _init_funding_adapters()

    print(f"[COMBO] Стратегии: funding={cfg.ALLOC_FUNDING_PCT*100:.0f}% "
          f"grid={cfg.ALLOC_GRID_PCT*100:.0f}% "
          f"momentum={cfg.ALLOC_MOMENTUM_PCT*100:.0f}%")
    print(f"[COMBO] Капитал: ${cfg.TOTAL_CAPITAL_USDT}")
    print(f"[COMBO] Kill порог: {cfg.GLOBAL_MAX_DRAWDOWN_PCT*100:.0f}%")

    async with aiohttp.ClientSession() as session:
        # Стартовое сообщение
        await _notify(
            session,
            combo_telegram._card("Комбо-бот запущен", "\U0001f680", [
                f"Капитал: ${cfg.TOTAL_CAPITAL_USDT:.0f}",
                f"Funding: {cfg.ALLOC_FUNDING_PCT*100:.0f}%",
                f"Grid: {cfg.ALLOC_GRID_PCT*100:.0f}%",
                f"Momentum: {cfg.ALLOC_MOMENTUM_PCT*100:.0f}%",
                f"Kill порог: {cfg.GLOBAL_MAX_DRAWDOWN_PCT*100:.0f}%",
            ]),
        )

        # Запускаем параллельно: main loop + Telegram polling
        await asyncio.gather(
            _main_loop(session, state),
            combo_telegram.polling_loop(session, state),
        )


if __name__ == "__main__":
    asyncio.run(main())
