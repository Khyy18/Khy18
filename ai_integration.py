"""Интеграция AI-модулей в combo-бот.

Связывает regime_classifier, signal_scorer и funding_predictor
с основным торговым циклом. Вызывается из combo_main на каждом тике.

Функции:
  - apply_regime_routing(): включает/выключает grid/momentum по режиму
  - score_momentum_signal(): оценивает качество сигнала перед входом
  - get_kelly_size(): масштабирует размер позиции по confidence
  - check_volume_exit(): проверяет anomaly для early exit
  - predict_funding_entry(): предсказывает funding для pre-entry timing
"""

from __future__ import annotations

import time
from typing import Any, Optional

import aiohttp

import combo_config as cfg
import regime_classifier
import signal_scorer


# ─── Regime Routing ────────────────────────────────────────────────────

async def apply_regime_routing(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: Any,
) -> dict[str, Any]:
    """Определить режим рынка и обновить enabled-состояние стратегий.

    Вызывается раз в 5 минут из combo_main. Проверяет режим по
    первому символу из GRID_SYMBOLS (как proxy всего рынка BTC).

    Возвращает dict с информацией о режиме для логирования.
    """
    g = state.get("global", {})
    last_regime_check = float(g.get("last_regime_check_epoch", 0))

    # Проверяем раз в 5 минут
    if (time.time() - last_regime_check) < 300:
        return {"skipped": "cooldown"}

    g["last_regime_check_epoch"] = time.time()

    # Берём свечи основного символа (BTC как proxy)
    symbol = cfg.GRID_SYMBOLS[0] if cfg.GRID_SYMBOLS else "BTCUSDT"
    try:
        klines = await adapter.get_klines(session, symbol, "15", limit=60)
    except Exception as exc:
        print(f"[AI-REGIME] klines error: {exc}")
        return {"error": str(exc)}

    if not klines or len(klines) < 30:
        return {"error": "недостаточно свечей"}

    # Классифицируем
    regime_info = regime_classifier.classify_regime(klines)

    # Сохраняем в state для UI
    g["current_regime"] = regime_info["regime"]
    g["regime_confidence"] = regime_info["confidence"]
    g["regime_adx"] = regime_info["adx"]

    # Маршрутизация (опционально — можно выключить через env)
    if g.get("auto_regime_routing", True):
        grid_state = state.get("grid", {})
        mom_state = state.get("momentum", {})

        should_grid = regime_classifier.should_enable_grid(regime_info)
        should_mom = regime_classifier.should_enable_momentum(regime_info)

        # Не отключаем если есть открытые позиции — только блокируем новые
        grid_state["regime_allows_new"] = should_grid
        mom_state["regime_allows_new"] = should_mom

        # Size multiplier
        g["regime_size_multiplier"] = regime_classifier.get_size_multiplier(regime_info)

    return regime_info


# ─── Signal Scoring ────────────────────────────────────────────────────

def score_momentum_entry(
    klines: list[dict[str, Any]],
    fast_ema: list[float],
    slow_ema: list[float],
    signal: str,
    min_score: float = 0.35,
) -> tuple[bool, float]:
    """Оценить качество momentum-сигнала.

    Returns:
        (should_enter, score): True если score >= min_score.
    """
    score = signal_scorer.compute_signal_score(
        klines, fast_ema, slow_ema, signal
    )
    return score >= min_score, score


# ─── Kelly Sizing ──────────────────────────────────────────────────────

def get_kelly_multiplier(
    signal_score: float,
    state: dict[str, Any],
) -> float:
    """Вычислить множитель размера позиции на основе signal score.

    Учитывает:
      - Signal confidence (score)
      - Regime size multiplier (VOLATILE → 0.5x)
      - Historical winrate (из state если есть)
    """
    g = state.get("global", {})
    regime_mult = float(g.get("regime_size_multiplier", 1.0))

    # Historical winrate из momentum stats
    mom_state = state.get("momentum", {})
    total_trades = int(mom_state.get("total_trades", 0))
    if total_trades > 10:
        # Считаем winrate из последних закрытых
        positions = mom_state.get("positions", [])
        closed = [p for p in positions if p.get("status") == "CLOSED"]
        if closed:
            wins = sum(1 for p in closed if float(p.get("pnl_usdt", 0)) > 0)
            winrate = wins / len(closed)
        else:
            winrate = 0.45
    else:
        winrate = 0.45  # дефолт до набора статистики

    kelly_mult = signal_scorer.kelly_fraction(
        signal_score=signal_score,
        winrate=winrate,
        avg_win=cfg.MOMENTUM_TAKE_PROFIT_PCT,
        avg_loss=cfg.MOMENTUM_STOP_LOSS_PCT,
    )

    # Итоговый множитель = kelly × regime
    return kelly_mult * regime_mult


# ─── Volume Anomaly Exit ───────────────────────────────────────────────

def check_volume_anomaly_exit(
    klines: list[dict[str, Any]],
    position_side: str,
) -> bool:
    """Проверить нужно ли закрыть позицию из-за volume anomaly.

    Делегирует в signal_scorer.detect_volume_anomaly_exit().
    """
    return signal_scorer.detect_volume_anomaly_exit(
        klines=klines,
        position_side=position_side,
        z_threshold=2.5,
        lookback=20,
    )


# ─── Funding Predictor ─────────────────────────────────────────────────

def predict_funding_bonus(
    state: dict[str, Any],
    symbol: str,
    exchange: str,
) -> float:
    """Предсказать бонус для funding-арб кандидата.

    Если predicted delta > 0 для SHORT-кандидата → бонус (funding вырастет).
    Если predicted delta < 0 для LONG-кандидата → бонус.

    Возвращает multiplier 0.8..1.2 для scoring арб-кандидата.
    """
    try:
        import funding_predictor
        import funding_history

        # Загружаем историю funding для символа
        history = funding_history.get_symbol_history(exchange, symbol, hours=24)
        if not history or len(history) < 10:
            return 1.0  # нет данных — нейтральный

        features = funding_predictor.extract_features(history)
        if features is None:
            return 1.0

        # Предсказываем
        model = funding_predictor.load_model()
        if model is None:
            return 1.0

        delta = funding_predictor.predict_delta(model, features)
        if delta is None:
            return 1.0

        # delta > 0 = rate вырастет = SHORT perp будет получать больше
        # Бонус для кандидатов которые совпадают с прогнозом
        bonus = 1.0 + min(0.2, max(-0.2, delta * 10))  # clamp ±20%
        return bonus

    except Exception:
        return 1.0
