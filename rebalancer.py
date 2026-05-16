"""Rebalancer — monitoring + advisor балансов USDT по биржам.

ВАЖНО: модуль НЕ выполняет автоматических withdraw'ов. Это сознательное
решение: автоматический withdraw — самый опасный код в боте, любой баг
ведёт к прямой потере средств. На MVP бот ограничивается ролью советника:

    1. Раз в REBALANCE_CHECK_INTERVAL_SEC опрашивает USDT-балансы всех
       активных бирж (через adapter.get_balance(session, "USDT")).
    2. Считает target = total / N_active и относительные отклонения.
    3. Если у любой биржи |deviation| > REBALANCE_THRESHOLD_PCT —
       формирует жадный план переводов (самая жирная → самой пустой)
       и присылает его в Telegram. Реальные withdraw'ы делает
       пользователь руками.

Анти-спам: один и тот же план не отправляется чаще раз в
REBALANCE_ALERT_COOLDOWN_SEC. Ключ дедупликации — отсортированный список
переводов, округлённых до ближайших 50 USDT (чтобы мелкие колебания
рынка не считались "новым планом").
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Optional

import config


# Тип одного рекомендованного перевода: (откуда, куда, сколько USDT).
TransferPlan = list[tuple[str, str, float]]


# Round-bucket для ключа дедупликации: 50 USDT.
# Должен совпадать с REBALANCE_MIN_TRANSFER_USDT по умолчанию, чтобы
# колебания меньше шага не порождали "новых" планов.
_PLAN_KEY_BUCKET_USDT = 50.0


async def _fetch_balances(
    session: Any,
    adapters: dict[str, Any],
) -> dict[str, float]:
    """Опрос USDT-балансов с активных бирж.

    Биржи, которые ответили None (ошибка/нет ключей) — пропускаются.
    Это безопасно: лучше не предлагать перевод, чем предлагать на основе
    битого баланса.
    """
    out: dict[str, float] = {}
    for name, adapter in adapters.items():
        try:
            bal = await adapter.get_balance(session, "USDT")
        except Exception as exc:  # noqa: BLE001
            print(f"[REBAL] {name}: get_balance исключение, пропуск: {exc}")
            continue
        if bal is None:
            print(f"[REBAL] {name}: get_balance вернул None, пропуск")
            continue
        try:
            out[name] = float(bal)
        except (TypeError, ValueError):
            print(f"[REBAL] {name}: невалидный баланс {bal!r}, пропуск")
    return out


def _build_transfer_plan(
    balances: dict[str, float],
    threshold_pct: float,
    min_transfer_usdt: float,
) -> TransferPlan:
    """Жадный план переводов из самой жирной биржи в самую пустую.

    Логика:
      - target = total / N
      - excess[ex]  = max(0, balance[ex] - target) — сколько ex может отдать
      - deficit[ex] = max(0, target - balance[ex]) — сколько ex может принять
      - Алгоритм: сортируем по deviation. Самой жирной отдаём всё
        возможное самой пустой, далее по списку.
      - Если ни одно отклонение не превышает threshold_pct — возвращаем
        пустой список (пользователь не будет дёргаться по мелочи).
      - Переводы < min_transfer_usdt не предлагаем.
    """
    if not balances:
        return []

    n = len(balances)
    total = sum(balances.values())
    if total <= 0 or n <= 1:
        return []

    target = total / n
    if target <= 0:
        return []

    # Проверяем, нужен ли вообще ребаланс. Если все в пределах threshold —
    # отдаём пустой план. В противном случае строим список.
    max_dev = 0.0
    for bal in balances.values():
        dev = abs(bal - target) / target
        if dev > max_dev:
            max_dev = dev
    if max_dev <= threshold_pct:
        return []

    # Сортируем биржи: самые жирные сверху (отрицательный excess отбрасываем),
    # самые пустые снизу (отрицательный deficit отбрасываем).
    sorted_excess: list[tuple[str, float]] = sorted(
        ((name, bal - target) for name, bal in balances.items() if bal - target > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )
    sorted_deficit: list[tuple[str, float]] = sorted(
        ((name, target - bal) for name, bal in balances.items() if target - bal > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )

    plan: TransferPlan = []
    excess_iter = list(sorted_excess)
    deficit_iter = list(sorted_deficit)
    i = 0  # указатель на жирные
    j = 0  # указатель на пустые

    # Используем мутируемые списки [name, remaining] для удобной "распилки"
    # текущей пары без копирования всех элементов.
    excess_list: list[list[Any]] = [[n, v] for n, v in excess_iter]
    deficit_list: list[list[Any]] = [[n, v] for n, v in deficit_iter]

    while i < len(excess_list) and j < len(deficit_list):
        from_ex, ex_remaining = excess_list[i]
        to_ex, def_remaining = deficit_list[j]
        amount = min(ex_remaining, def_remaining)

        if amount >= min_transfer_usdt:
            plan.append((from_ex, to_ex, float(amount)))

        excess_list[i][1] = ex_remaining - amount
        deficit_list[j][1] = def_remaining - amount

        # Двигаем указатели — кто опустошился, того и листаем.
        if excess_list[i][1] <= 1e-9:
            i += 1
        if deficit_list[j][1] <= 1e-9:
            j += 1

    return plan


def _plan_dedup_key(plan: TransferPlan) -> str:
    """Стабильный ключ для cooldown-дедупликации.

    Округляем суммы до ближайших _PLAN_KEY_BUCKET_USDT, сортируем — чтобы
    мелкие колебания (300 USDT vs 312 USDT) не считались разными планами
    и не спамили в Telegram.
    """
    rounded: list[tuple[str, str, int]] = []
    for from_ex, to_ex, amount in plan:
        bucket = max(
            int(_PLAN_KEY_BUCKET_USDT),
            int(round(amount / _PLAN_KEY_BUCKET_USDT) * _PLAN_KEY_BUCKET_USDT),
        )
        rounded.append((from_ex, to_ex, bucket))
    rounded.sort()
    return "|".join(f"{a}>{b}:{c}" for a, b, c in rounded)


def _format_alert(
    balances: dict[str, float],
    target: float,
    plan: TransferPlan,
    cooldown_sec: float,
) -> str:
    """Сформировать текст алерта для Telegram (HTML + моноширинные блоки)."""
    n = len(balances)
    total = sum(balances.values())

    # Сортируем биржи по deviation (от пустых к жирным) — так перекосы
    # сразу бросаются в глаза.
    rows: list[tuple[str, float, float]] = []
    for name, bal in balances.items():
        dev = (bal - target) / target if target > 0 else 0.0
        rows.append((name, bal, dev))
    rows.sort(key=lambda kv: kv[2])

    # Ширина колонок: имя биржи до 8 символов, баланс до 8 знаков.
    body_lines: list[str] = []
    for name, bal, dev in rows:
        marker = ""
        if dev <= -0.30:
            marker = "  <- пустая"
        elif dev >= 0.30:
            marker = "  <- полная"
        body_lines.append(
            f"  {name:<8} {bal:>8.2f}  ({dev*100:+.0f}%){marker}"
        )

    # Рекомендации: округляем до целых USDT и пишем в столбик.
    plan_lines: list[str] = []
    for from_ex, to_ex, amount in plan:
        plan_lines.append(
            f"  {from_ex} -> {to_ex}: {amount:.0f} USDT (BSC)"
        )

    cooldown_h = cooldown_sec / 3600.0
    cooldown_str = (
        f"{int(cooldown_h)}ч" if cooldown_h >= 1 else f"{int(cooldown_sec / 60)}мин"
    )

    parts = [
        "<b>Rebalance recommended</b>",
        "",
        f"Total USDT ({n} exchanges): {total:.2f}",
        f"Target per exchange: {target:.2f}",
        "",
        "Перекосы:",
        "<pre>" + "\n".join(body_lines) + "</pre>",
        "Рекомендованные переводы:",
        "<pre>" + "\n".join(plan_lines) + "</pre>",
        f"Алерт повторится через {cooldown_str}.",
    ]
    return "\n".join(parts)


async def check_and_alert(
    session: Any,
    adapters: dict[str, Any],
    notify: Callable[[str], Awaitable[None]],
    state: dict[str, Any],
) -> Optional[TransferPlan]:
    """Один проход ребалансера.

    Возвращает список рекомендованных переводов или None, если всё ок
    или если не удалось получить балансы хотя бы с двух бирж.

    state используется только для cooldown-дедупликации:
      state["rebalance_alert_seen"] = {plan_key: epoch_ts}.
    """
    threshold_pct = float(getattr(config, "REBALANCE_THRESHOLD_PCT", 0.30))
    min_transfer = float(getattr(config, "REBALANCE_MIN_TRANSFER_USDT", 50.0))
    cooldown_sec = float(getattr(config, "REBALANCE_ALERT_COOLDOWN_SEC", 6 * 3600.0))

    balances = await _fetch_balances(session, adapters)
    if len(balances) < 2:
        # На одной бирже ребалансировать нечего, на нуле — тем более.
        print(f"[REBAL] балансов получено {len(balances)}, пропуск")
        return None

    plan = _build_transfer_plan(balances, threshold_pct, min_transfer)
    if not plan:
        return None

    # Cooldown.
    seen: dict[str, float] = state.get("rebalance_alert_seen") or {}
    key = _plan_dedup_key(plan)
    last_ts = float(seen.get(key) or 0.0)
    now = time.time()
    if (now - last_ts) < cooldown_sec:
        # Тот же план уже отправлялся недавно — не спамим.
        return plan

    target = sum(balances.values()) / len(balances)
    text = "\u2696\ufe0f " + _format_alert(balances, target, plan, cooldown_sec)
    try:
        await notify(text)
    except Exception as exc:  # noqa: BLE001
        # Если Telegram отвалился — не тушим план, просто не помечаем
        # как доставленный (попробуем в следующий тик).
        print(f"[REBAL] notify fail: {exc}")
        return plan

    seen[key] = now
    state["rebalance_alert_seen"] = seen
    return plan
