"""Lending advisor — рекомендации по подписке простаивающего USDT в Earn-flex.

ВАЖНО: модуль НЕ выполняет автоматических подписок в Earn-продукты.
Это сознательное решение: подписка/выкуп — отдельный класс биржевых
API (Earn/Savings) с собственными лимитами, минимумами и рисками.
На MVP бот ограничивается ролью советника:

    1. Раз в LENDING_CHECK_INTERVAL_SEC опрашивает USDT-балансы всех
       активных бирж (через adapter.get_balance(session, "USDT")).
    2. Считает margin_in_use для каждой биржи: сумма
       (notional / leverage) по всем активным арб-парам, где эта биржа
       задействована (LONG- или SHORT-нога).
    3. Считает резерв: max(LENDING_RESERVE_PCT * total_balance,
       LENDING_MIN_RESERVE_USDT). 30% по умолчанию + минимум 50 USDT.
    4. idle = free_usdt - margin_in_use - reserve.
    5. Если idle > LENDING_IDLE_THRESHOLD_USDT — добавляет биржу в план
       подписки. Если у всех бирж idle <= threshold — план пустой,
       алерт не отправляется.

Анти-спам: один и тот же план не отправляется чаще раз в
LENDING_ALERT_COOLDOWN_SEC (24ч по умолчанию). Ключ дедупликации —
отсортированный список рекомендаций, округлённых до ближайших 50 USDT,
чтобы мелкие колебания рынка не считались "новым планом".

Подписываться рекомендуется ТОЛЬКО во flex-продукты (выводимые мгновенно),
чтобы маржа была доступна на funding-tick. Lock-продукты с фиксированным
сроком подписки могут заблокировать средства в неподходящий момент.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Optional

import arb_storage
import config


# Тип одной рекомендации: (биржа, idle_usdt, free_usdt, margin_in_use, reserve).
LendingPlanItem = tuple[str, float, float, float, float]
LendingPlan = list[LendingPlanItem]


# Round-bucket для ключа дедупликации: 50 USDT.
# Должен совпадать с LENDING_MIN_RESERVE_USDT по умолчанию, чтобы
# колебания меньше шага не порождали "новых" планов.
_PLAN_KEY_BUCKET_USDT = 50.0


async def _fetch_balances(
    session: Any,
    adapters: dict[str, Any],
) -> dict[str, float]:
    """Опрос USDT-балансов с активных бирж.

    Биржи, которые ответили None (ошибка/нет ключей) — пропускаются.
    Это безопасно: лучше не предлагать подписку, чем считать idle на
    основе битого баланса.
    """
    out: dict[str, float] = {}
    for name, adapter in adapters.items():
        try:
            bal = await adapter.get_balance(session, "USDT")
        except Exception as exc:  # noqa: BLE001
            print(f"[LEND] {name}: get_balance исключение, пропуск: {exc}")
            continue
        if bal is None:
            print(f"[LEND] {name}: get_balance вернул None, пропуск")
            continue
        try:
            out[name] = float(bal)
        except (TypeError, ValueError):
            print(f"[LEND] {name}: невалидный баланс {bal!r}, пропуск")
    return out


def _margin_in_use_per_exchange(
    active_positions: list[dict[str, Any]],
    leverage: float,
) -> dict[str, float]:
    """Сколько USDT-маржи используется на каждой бирже под активные пары.

    Для каждой пары: margin_per_leg = notional_usdt / leverage. Каждая
    биржа держит ОДНУ ногу (LONG ИЛИ SHORT), поэтому к каждой бирже из
    pair прибавляем margin одной ноги.
    """
    out: dict[str, float] = {}
    if leverage <= 0:
        leverage = 1.0
    for pos in active_positions:
        try:
            notional = float(pos.get("notional_usdt") or 0.0)
        except (TypeError, ValueError):
            continue
        if notional <= 0:
            continue
        margin = notional / leverage
        for key in ("long_exchange", "short_exchange"):
            ex = str(pos.get(key) or "").lower()
            if ex:
                out[ex] = out.get(ex, 0.0) + margin
    return out


def _build_lending_plan(
    balances: dict[str, float],
    margins: dict[str, float],
    reserve_pct: float,
    min_reserve_usdt: float,
    idle_threshold_usdt: float,
) -> LendingPlan:
    """Сформировать список рекомендаций подписки.

    Логика для каждой биржи:
      reserve   = max(reserve_pct * balance, min_reserve_usdt)
      idle      = balance - margin_in_use - reserve
      Если idle > idle_threshold_usdt — добавляем (ex, idle, balance,
      margin, reserve) в план.

    Резерв считается ОТ свободного баланса конкретной биржи (а не от
    суммарного по всем биржам): иначе на маленькой бирже резерв был бы
    несоразмерно велик и idle всегда был бы ноль.
    """
    plan: LendingPlan = []
    for ex, bal in balances.items():
        margin = float(margins.get(ex, 0.0))
        reserve_dynamic = bal * reserve_pct
        reserve = max(reserve_dynamic, min_reserve_usdt)
        idle = bal - margin - reserve
        if idle > idle_threshold_usdt:
            plan.append((ex, float(idle), float(bal), float(margin), float(reserve)))
    # Сортировка по убыванию idle: самая жирная биржа сверху.
    plan.sort(key=lambda x: x[1], reverse=True)
    return plan


def _plan_dedup_key(plan: LendingPlan) -> str:
    """Стабильный ключ для cooldown-дедупликации.

    Округляем idle до ближайших _PLAN_KEY_BUCKET_USDT, сортируем — чтобы
    мелкие колебания (180 USDT vs 192 USDT) не считались разными планами
    и не спамили в Telegram.
    """
    rounded: list[tuple[str, int]] = []
    for ex, idle, _bal, _margin, _reserve in plan:
        bucket = max(
            int(_PLAN_KEY_BUCKET_USDT),
            int(round(idle / _PLAN_KEY_BUCKET_USDT) * _PLAN_KEY_BUCKET_USDT),
        )
        rounded.append((ex, bucket))
    rounded.sort()
    return "|".join(f"{a}:{b}" for a, b in rounded)


def _format_alert(plan: LendingPlan, cooldown_sec: float) -> str:
    """Сформировать текст алерта для Telegram (HTML + моноширинный блок).

    Формат:
      💸 Lending advisor

      На биржах простаивает USDT, который можно подписать в Earn flex
      (4-12% APR дополнительно). Рекомендации:

        bybit:    220 USDT (free 350 - margin 60 - reserve 70)
        ...

      Итого: 550 USDT в Earn ≈ +30-65 USDT/год без дополнительного риска.
      ...
    """
    body_lines: list[str] = []
    for ex, idle, bal, margin, reserve in plan:
        body_lines.append(
            f"  {ex:<8} {idle:>5.0f} USDT (free {bal:.0f} - margin "
            f"{margin:.0f} - reserve {reserve:.0f})"
        )

    total_idle = sum(item[1] for item in plan)
    # Оценка прибавки: 4-12% APR от total_idle.
    yield_low = total_idle * 0.04
    yield_high = total_idle * 0.12

    cooldown_h = cooldown_sec / 3600.0
    cooldown_str = (
        f"{int(cooldown_h)}ч" if cooldown_h >= 1 else f"{int(cooldown_sec / 60)}мин"
    )

    parts = [
        "\U0001f4b8 <b>Lending advisor</b>",
        "",
        "На биржах простаивает USDT, который можно подписать в Earn flex "
        "(4-12% APR дополнительно). Рекомендации:",
        "",
        "<pre>" + "\n".join(body_lines) + "</pre>",
        f"Итого: {total_idle:.0f} USDT в Earn \u2248 +{yield_low:.0f}-{yield_high:.0f} "
        f"USDT/год без дополнительного риска.",
        "",
        "Подписывайтесь только во flex-продукты (выводимые мгновенно), чтобы "
        "маржа была доступна на funding-tick. "
        f"Алерт повторится через {cooldown_str}.",
    ]
    return "\n".join(parts)


async def check_idle_balances(
    session: Any,
    adapters: dict[str, Any],
    notify: Callable[[str], Awaitable[None]],
    state: dict[str, Any],
) -> Optional[list[dict[str, Any]]]:
    """Один проход lending-advisor'а.

    Возвращает список рекомендаций (по одной на биржу с idle > threshold)
    либо None, если:
      - не удалось получить балансы хотя бы с одной биржи;
      - ни на одной бирже idle не превысил порог.

    Каждый элемент списка — dict со полями:
      exchange, idle, balance, margin_in_use, reserve.

    state используется только для cooldown-дедупликации:
      state["lending_alert_seen"] = {plan_key: epoch_ts}.
    """
    reserve_pct = float(getattr(config, "LENDING_RESERVE_PCT", 0.30))
    min_reserve = float(getattr(config, "LENDING_MIN_RESERVE_USDT", 50.0))
    idle_threshold = float(getattr(config, "LENDING_IDLE_THRESHOLD_USDT", 100.0))
    cooldown_sec = float(getattr(config, "LENDING_ALERT_COOLDOWN_SEC", 24 * 3600.0))
    leverage = max(1.0, float(getattr(config, "ARB_LEVERAGE", 3.0)))

    balances = await _fetch_balances(session, adapters)
    if not balances:
        print("[LEND] балансов получено 0, пропуск")
        return None

    # Активные арб-пары — для расчёта margin_in_use на каждой бирже.
    try:
        active_positions = arb_storage.get_all_active() or []
    except Exception as exc:  # noqa: BLE001
        print(f"[LEND] arb_storage.get_all_active fail: {exc}")
        active_positions = []

    margins = _margin_in_use_per_exchange(active_positions, leverage)

    plan = _build_lending_plan(
        balances, margins, reserve_pct, min_reserve, idle_threshold,
    )
    if not plan:
        return None

    # Cooldown.
    seen: dict[str, float] = state.get("lending_alert_seen") or {}
    key = _plan_dedup_key(plan)
    last_ts = float(seen.get(key) or 0.0)
    now = time.time()
    plan_dicts = [
        {
            "exchange": ex,
            "idle": idle,
            "balance": bal,
            "margin_in_use": margin,
            "reserve": reserve,
        }
        for ex, idle, bal, margin, reserve in plan
    ]
    if (now - last_ts) < cooldown_sec:
        # Тот же план уже отправлялся недавно — не спамим, но возвращаем
        # рекомендации (для отладки/UI).
        return plan_dicts

    text = _format_alert(plan, cooldown_sec)
    try:
        await notify(text)
    except Exception as exc:  # noqa: BLE001
        # Если Telegram отвалился — не тушим план, просто не помечаем
        # как доставленный (попробуем в следующий тик).
        print(f"[LEND] notify fail: {exc}")
        return plan_dicts

    seen[key] = now
    state["lending_alert_seen"] = seen
    return plan_dicts
