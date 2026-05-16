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

    async def handle_pre_checkout_query(
        self, session, query_id: str, invoice_payload: str = ""
    ) -> bool:
        """Подтвердить pre_checkout_query после валидации инвойса.

        Проверяет что invoice_payload соответствует существующему pending-инвойсу.
        Если валидация не проходит - отвечает ok=False с описанием ошибки.
        """
        # Validate the invoice exists and is pending
        ok = True
        error_message = ""
        try:
            invoice_id = int(invoice_payload)
            invoice = models.get_invoice(invoice_id)
            if invoice is None:
                ok = False
                error_message = "Invoice not found"
            elif invoice["status"] != "pending":
                ok = False
                error_message = "Invoice is no longer pending"
        except (ValueError, TypeError):
            ok = False
            error_message = "Invalid invoice payload"

        payload: dict = {
            "pre_checkout_query_id": query_id,
            "ok": ok,
        }
        if not ok:
            payload["error_message"] = error_message

        url = self._bot_url("answerPreCheckoutQuery")
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            return data.get("ok", False)

    async def handle_successful_payment(
        self, update: dict, session=None
    ) -> Optional[int]:
        """Обработать successful_payment из Telegram update.

        Помечает инвойс как оплаченный, вызывает бонус реферала и
        генерацию оферты при первом платеже. Возвращает invoice_id.
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
        if not success:
            return None

        # Extract user info from update
        from_user = message.get("from", {})
        user_tg_id = from_user.get("id", 0)
        user_name = (
            from_user.get("first_name", "")
            or from_user.get("username", "User")
        )

        # Get invoice details for amount/description
        invoice = models.get_invoice(invoice_id)
        amount = invoice["amount_stars"] if invoice else 0
        description = invoice.get("description", "") if invoice else ""

        # Wire referral bonus (conditional import)
        try:
            from viral.models import grant_bonus_on_payment
        except ImportError:
            pass
        else:
            try:
                grant_bonus_on_payment(user_tg_id)
            except Exception:
                pass

        # Wire legal integration (conditional import)
        try:
            from legal.integration import on_first_payment
        except ImportError:
            pass
        else:
            try:
                if session:
                    await on_first_payment(
                        session, user_tg_id, user_name, amount, description
                    )
            except Exception:
                pass

        return invoice_id
