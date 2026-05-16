"""Audit log command handler - shows last 10 audit actions from backend."""

import httpx
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from kindergarten_accountant_bot.config import BACKEND_URL, BACKEND_TOKEN
from kindergarten_accountant_bot.utils.formatting import _card
from kindergarten_accountant_bot.utils.roles import require_roles


@require_roles("admin", "director")
async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch and display last 10 audit log entries from backend."""
    headers = {}
    if BACKEND_TOKEN:
        headers["Authorization"] = f"Bearer {BACKEND_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/v1/audit",
                params={"limit": 10},
                headers=headers,
            )
            resp.raise_for_status()
            entries = resp.json()
    except Exception:
        await update.message.reply_text("Не удалось получить журнал аудита. Бэкенд недоступен.")
        return

    if not entries:
        await update.message.reply_text("Журнал аудита пуст.")
        return

    body_lines = []
    for entry in entries:
        action = entry.get("action", "?")
        entity = entry.get("entity_type", "?")
        ts = entry.get("timestamp", "")[:16]  # trim to YYYY-MM-DD HH:MM
        user = entry.get("user_id", "-")
        body_lines.append(f"{ts} | {action} | {entity} | {user}")

    card = _card("Журнал аудита", "\U0001f4cb", body_lines)
    await update.message.reply_text(card, parse_mode="HTML")


audit_handler = CommandHandler("audit", audit_command)
