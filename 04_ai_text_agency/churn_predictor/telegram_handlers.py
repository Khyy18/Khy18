"""Telegram handlers for churn risk monitoring."""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import config
from churn_predictor.predictor import ChurnPredictor
from logging_config import get_logger

log = get_logger(__name__)


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


async def _send_message(
    session: aiohttp.ClientSession,
    chat_id: int,
    text: str,
) -> Optional[dict[str, Any]]:
    """Send a message via Telegram Bot API."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as e:
        log.error("telegram_send_error", error=str(e), chat_id=chat_id)
        return None


async def handle_churn_risk_command(
    session: aiohttp.ClientSession,
    chat_id: int,
) -> None:
    """Handle /churn_risk command - show top at-risk clients."""
    from crm.models import list_clients_by_stage

    predictor = ChurnPredictor()

    # Gather all clients from all stages
    all_clients = []
    for stage in ("lead", "trial", "paid", "churned"):
        clients = list_clients_by_stage(stage)
        all_clients.extend(clients)

    if not all_clients:
        await _send_message(session, chat_id, "Нет клиентов в базе CRM.")
        return

    # Compute risk for each
    risk_data: list[tuple[dict, float]] = []
    for client in all_clients:
        features = predictor.compute_features(client["tg_id"])
        risk = predictor.predict(features)
        risk_data.append((client, risk))

    # Sort by risk descending
    risk_data.sort(key=lambda x: x[1], reverse=True)

    # Show top 10
    lines = ["<b>Топ-10 клиентов с риском оттока:</b>\n"]
    for i, (client, risk) in enumerate(risk_data[:10], 1):
        risk_pct = int(risk * 100)
        emoji = "🔴" if risk > 0.7 else "🟡" if risk > 0.5 else "🟢"
        lines.append(
            f"{i}. {emoji} {client['name']} "
            f"(tg: {client['tg_id']}) - {risk_pct}% [{client['stage']}]"
        )

    text = "\n".join(lines)
    await _send_message(session, chat_id, text)
    log.info("churn_risk_report_sent", chat_id=chat_id, total_clients=len(all_clients))
