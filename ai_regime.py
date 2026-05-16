"""Классификатор рыночного режима: TRENDING / RANGING / CRISIS.

Вход - до 30 дневных OHLC-свечей, актуальная ATR(1h), 30-дневная
реализованная волатильность и до 10 свежих заголовков. Groq возвращает
строгий JSON {regime, confidence, reason}.

Политика отказоустойчивости - **fail-CLOSED**: при любой ошибке ставим
regime=CRISIS с нулевой уверенностью. CRISIS блокирует входы в strategy_v2,
поэтому сбой классификатора корректно «замораживает» бота до следующего
валидного ответа или ручного вмешательства.

Кэш - отдельный на символ, TTL = config.AI_REGIME_TTL_SEC. Кэшируем и
fail-closed результат, чтобы не ddos-ить Groq при длительных сбоях.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

import ai_groq
import config


_CACHE: dict[str, dict[str, Any]] = {}

_ALLOWED_REGIMES = ("TRENDING", "RANGING", "CRISIS")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def clear_cache(symbol: Optional[str] = None) -> None:
    """Сбросить кэш. Без аргумента - чистит всё, с symbol - только его."""
    if symbol is None:
        _CACHE.clear()
        return
    _CACHE.pop(str(symbol), None)


def _fail_closed(symbol: str) -> dict[str, Any]:
    value = {
        "regime": "CRISIS",
        "confidence": 0,
        "reason": "Ошибка классификатора, считаем CRISIS",
        "ts": _now_iso(),
        "symbol": str(symbol),
    }
    _CACHE[str(symbol)] = {"ts_epoch": time.time(), **value}
    return dict(value)


def _format_ts(ts: Any) -> str:
    """Нормализовать ts к короткой дате 'YYYY-MM-DD'. Поддерживаем int (мс/с)
    и ISO-строки. В крайнем случае вернём как есть."""
    if ts is None:
        return "-"
    if isinstance(ts, (int, float)):
        try:
            # Предполагаем миллисекунды, если значение больше 10^12.
            val = float(ts)
            if val > 1e12:
                val /= 1000.0
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return str(ts)
    s = str(ts).strip()
    if not s:
        return "-"
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d")
    except ValueError:
        return s[:10]


def _format_ohlc_block(daily_ohlc: list[dict[str, Any]]) -> str:
    trimmed = list(daily_ohlc or [])[-30:]
    rows = []
    for row in trimmed:
        if not isinstance(row, dict):
            continue
        try:
            rows.append(
                "[{d}, {o}, {h}, {l}, {c}]".format(
                    d=_format_ts(row.get("ts")),
                    o=float(row.get("open", 0.0)),
                    h=float(row.get("high", 0.0)),
                    l=float(row.get("low", 0.0)),
                    c=float(row.get("close", 0.0)),
                )
            )
        except (TypeError, ValueError):
            continue
    return "\n".join(rows) if rows else "(нет данных)"


def _build_prompt(
    symbol: str,
    daily_ohlc: list[dict[str, Any]],
    atr_1h: float,
    realized_vol_30d: float,
    headlines: list[str],
) -> str:
    ohlc_block = _format_ohlc_block(daily_ohlc)
    hl_lines = []
    for i, h in enumerate((headlines or [])[:10], start=1):
        h_clean = str(h or "").strip().replace("\n", " ")
        if h_clean:
            hl_lines.append(f"{i}. {h_clean}")
    hl_block = "\n".join(hl_lines) if hl_lines else "(нет заголовков)"
    return (
        "Ты регимный классификатор. По данным классифицируй рыночный режим "
        f"для {symbol}: TRENDING (устойчивый направленный тренд), RANGING "
        "(боковик, без направления), CRISIS (высокая волатильность, паника, "
        "резкие движения). Верни СТРОГО JSON: "
        "{\"regime\": \"TRENDING\"|\"RANGING\"|\"CRISIS\", "
        "\"confidence\": 0-100, \"reason\": \"краткое обоснование\"}.\n\n"
        f"Символ: {symbol}\n"
        f"ATR(1h) актуальный: {atr_1h}\n"
        f"Реализованная волатильность 30d (годовая): {realized_vol_30d}\n"
        f"Дневные OHLC [date, open, high, low, close]:\n{ohlc_block}\n\n"
        f"Заголовки:\n{hl_block}\n"
    )


async def classify(
    session: aiohttp.ClientSession,
    symbol: str,
    daily_ohlc: list[dict[str, Any]],
    atr_1h: float,
    realized_vol_30d: float,
    headlines: list[str],
) -> dict[str, Any]:
    """Классифицировать рыночный режим. Fail-CLOSED -> CRISIS."""
    sym = str(symbol or "-")
    try:
        ttl = float(getattr(config, "AI_REGIME_TTL_SEC", 0) or 0)
        cached = _CACHE.get(sym)
        if cached and (time.time() - float(cached.get("ts_epoch", 0.0))) < ttl:
            out = {k: v for k, v in cached.items() if k != "ts_epoch"}
            return out
    except Exception as exc:  # noqa: BLE001
        print(f"[REGIME] Сбой чтения кэша: {exc}")

    try:
        prompt = _build_prompt(
            sym, daily_ohlc or [], atr_1h, realized_vol_30d, headlines or []
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[REGIME] Ошибка построения промпта: {exc}")
        return _fail_closed(sym)

    try:
        parsed: Optional[dict[str, Any]] = await ai_groq.call_groq_json(
            session, prompt
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[REGIME] Ошибка вызова Groq: {exc}")
        return _fail_closed(sym)

    if not isinstance(parsed, dict):
        print("[REGIME] Groq не вернул валидный JSON - fail-closed")
        return _fail_closed(sym)

    try:
        regime_raw = str(parsed.get("regime", "")).strip().upper()
        regime = regime_raw if regime_raw in _ALLOWED_REGIMES else "CRISIS"

        try:
            conf_num = int(float(parsed.get("confidence", 0)))
        except (TypeError, ValueError):
            conf_num = 0
        confidence = max(0, min(100, conf_num))

        reason = str(parsed.get("reason", "") or "").strip()[:200]
        if not reason:
            reason = "без пояснения"
    except Exception as exc:  # noqa: BLE001
        print(f"[REGIME] Ошибка нормализации ответа Groq: {exc}")
        return _fail_closed(sym)

    value = {
        "regime": regime,
        "confidence": confidence,
        "reason": reason,
        "ts": _now_iso(),
        "symbol": sym,
    }
    _CACHE[sym] = {"ts_epoch": time.time(), **value}
    return dict(value)
