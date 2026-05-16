"""Сервис платежей через Telegram Stars.

Использует Telegram Bot API: createInvoiceLink, answerPreCheckoutQuery.
Валюта XTR = Telegram Stars.
"""

from __future__ import annotations

import os
from typing import Optional

from payments import models


class PaymentService:
    """Обработка платежей через Telegram Stars."""

    def __init__(self, token: str = None):
        self.token = token or os.getenv("TELEGRAM_TOKEN", "")

    def _bot_url(self, method: str) -> str:
        """Сформировать URL для вызова метода Telegram Bot API."""
        return f"https://api.telegram.org/bot{self.token}/{method}"

    async def create_invoice_link(
        self,
        session,
        user_tg_id: int,
        amount_stars: int,
        title: str,
        description: str,
    ) -> Optional[str]:
        """Создать ссылку на инвойс через Telegram Bot API.

        Записывает инвойс в БД и возвращает URL для оплаты.
        """
        # Сохраняем инвойс в БД
        invoice_id = models.create_invoice(user_tg_id, amount_stars, description)

        payload = {
            "title": title,
            "description": description,
            "payload": str(invoice_id),
            "currency": "XTR",
            "prices": [{"label": title, "amount": amount_stars}],
        }

        url = self._bot_url("createInvoiceLink")
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]
            return None

    async def handle_pre_checkout_query(self, session, query_id: str) -> bool:
        """Подтвердить pre_checkout_query (ответить ok=True)."""
        payload = {
            "pre_checkout_query_id": query_id,
            "ok": True,
        }
        url = self._bot_url("answerPreCheckoutQuery")
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            return data.get("ok", False)

    async def handle_successful_payment(self, update: dict) -> Optional[int]:
        """Обработать successful_payment из Telegram update.

        Помечает инвойс как оплаченный и возвращает invoice_id.
        """
        message = update.get("message", {})
        payment = message.get("successful_payment")
        if not payment:
            return None

        invoice_payload = payment.get("invoice_payload", "")
        charge_id = payment.get("telegram_payment_charge_id", "")

        try:
            invoice_id = int(invoice_payload)
        except (ValueError, TypeError):
            return None

        success = models.mark_paid(invoice_id, charge_id)
        return invoice_id if success else None
