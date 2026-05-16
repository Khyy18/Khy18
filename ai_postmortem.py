"""Еженедельный пост-мортем: свободный отчёт на русском языке.

Читает сделки и equity-кривую за последние N дней из memory, собирает
компактную сводку и просит Groq написать связный текст (без JSON).
Кэша нет - вызов происходит редко (раз в неделю по расписанию или по
кнопке Telegram).

При любой ошибке или пустом ответе Groq возвращаем ровно строку
'Отчёт временно недоступен.' - наверху её показываем пользователю
как есть.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiohttp

import ai_groq
import memory


_FAIL_TEXT = "Отчёт временно недоступен."
_MAX_OUTPUT_CHARS = 2000


def _format_trade_ts(ts: Any) -> str:
    """Привести метку времени к 'dd-mm HH:MM' или вернуть как строку."""
    if ts is None:
        return "??"
    s = str(ts).strip()
    if not s:
        return "??"
    try:
        return datetime.fromisoformat(s).strftime("%d-%m %H:%M")
    except ValueError:
        return s[:16]


def _summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [t for t in trades if str(t.get("outcome", "")).upper() in ("WIN", "LOSS")]
    wins = sum(1 for t in closed if str(t.get("outcome", "")).upper() == "WIN")
    losses = sum(1 for t in closed if str(t.get("outcome", "")).upper() == "LOSS")
    pnls = []
    for t in closed:
        try:
            pnls.append(float(t.get("pnl") or 0.0))
        except (TypeError, ValueError):
            continue
    best = max(pnls) if pnls else 0.0
    worst = min(pnls) if pnls else 0.0
    return {
        "total": len(closed),
        "wins": wins,
        "losses": losses,
        "best_pnl": round(best, 4),
        "worst_pnl": round(worst, 4),
    }


def _format_trade_lines(trades: list[dict[str, Any]]) -> str:
    # Берём до 20 самых свежих. memory.get_trades_since отдаёт ASC, поэтому
    # хвост списка - самое новое.
    tail = list(trades)[-20:]
    lines = []
    for t in tail:
        try:
            lines.append(
                "{ts} {sym} {side} pnl={pnl} {outcome}".format(
                    ts=_format_trade_ts(t.get("closed_ts") or t.get("ts")),
                    sym=str(t.get("symbol") or "-"),
                    side=str(t.get("side") or "-"),
                    pnl=t.get("pnl") if t.get("pnl") is not None else "-",
                    outcome=str(t.get("outcome") or "-"),
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(lines) if lines else "(нет сделок за период)"


async def report(session: aiohttp.ClientSession, days: int = 7) -> str:
    """Собрать и вернуть пост-мортем отчёт по сделкам за `days` суток."""
    try:
        trades = memory.get_trades_since(int(days))
    except Exception as exc:  # noqa: BLE001
        print(f"[POSTMORTEM] Ошибка чтения сделок: {exc}")
        return _FAIL_TEXT

    try:
        equity_curve = memory.get_equity_curve(int(days))
    except Exception as exc:  # noqa: BLE001
        print(f"[POSTMORTEM] Ошибка чтения equity_curve: {exc}")
        equity_curve = []

    try:
        current_dd = float(memory.get_current_drawdown() or 0.0)
    except Exception as exc:  # noqa: BLE001
        print(f"[POSTMORTEM] Ошибка расчёта текущей просадки: {exc}")
        current_dd = 0.0

    try:
        week_pnl = float(memory.get_week_pnl() or 0.0)
    except Exception as exc:  # noqa: BLE001
        print(f"[POSTMORTEM] Ошибка расчёта недельного PnL: {exc}")
        week_pnl = 0.0

    summary = _summarize(trades or [])
    summary_lines = (
        f"Период: последние {int(days)} сут.\n"
        f"Всего закрытых сделок: {summary['total']}\n"
        f"Побед: {summary['wins']}, поражений: {summary['losses']}\n"
        f"Лучшая сделка по PnL: {summary['best_pnl']}\n"
        f"Худшая сделка по PnL: {summary['worst_pnl']}\n"
        f"Текущая просадка: {round(current_dd, 4)}\n"
        f"Суммарный PnL за неделю: {round(week_pnl, 4)}\n"
        f"Точек equity-кривой: {len(equity_curve)}\n"
    )
    trade_block = _format_trade_lines(trades or [])

    prompt = (
        "Ты пост-мортем аналитик. По списку сделок за последнюю неделю "
        "напиши краткий отчёт на русском (не более 400 слов): что работало, "
        "где просадки, какие параметры стоит пересмотреть. Не пиши JSON, "
        "просто связный текст.\n\n"
        f"Сводка:\n{summary_lines}\n"
        f"Последние сделки (до 20):\n{trade_block}\n"
    )

    try:
        text = await ai_groq.call_groq_text(
            session,
            prompt,
            max_output_tokens=800,
            temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[POSTMORTEM] Ошибка вызова Groq: {exc}")
        return _FAIL_TEXT

    text = (text or "").strip()
    if not text:
        return _FAIL_TEXT
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS].rstrip()
    return text
