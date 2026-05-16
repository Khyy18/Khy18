"""AI handler for Telegram bot - free-text intent classification via Groq."""

import logging
import os
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from kindergarten_accountant_bot.utils.formatting import _card

logger = logging.getLogger(__name__)

# Backend URL for AI endpoint (can be overridden via environment)
AI_BACKEND_URL = os.environ.get("AI_BACKEND_URL", "http://localhost:8000/api/v1/ai/chat")


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle AI mode for the user with /ai command."""
    ai_mode = context.user_data.get("ai_mode", False)
    context.user_data["ai_mode"] = not ai_mode

    if not ai_mode:
        body_lines = [
            "AI-режим включён!",
            "",
            "Теперь вы можете писать запросы",
            "свободным текстом, например:",
            "",
            "- Рассчитай зарплату с окладом 30000",
            "- Сколько отпускных за 14 дней?",
            "- Найди КБК для НДФЛ",
            "- Какой срок сдачи 6-НДФЛ?",
            "",
            "Для выхода: /ai",
        ]
        card = _card("AI-ассистент", "\U0001f916", body_lines)
    else:
        body_lines = [
            "AI-режим выключен.",
            "Используйте меню для навигации.",
        ]
        card = _card("AI-ассистент", "\U0001f916", body_lines)

    await update.message.reply_text(card, parse_mode="HTML")


async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process free-text messages when AI mode is enabled.

    Calls the AI backend endpoint or directly uses Groq for classification.
    """
    if not context.user_data.get("ai_mode", False):
        return

    user_message = update.message.text
    if not user_message:
        return

    # Try calling the backend AI endpoint
    response_text = await _call_ai_backend(user_message, update.effective_chat.id)

    if response_text:
        # Format as card if it's a calculation result
        if any(keyword in response_text for keyword in ["Расчёт", "Найденные КБК"]):
            lines = response_text.split("\n")
            title = lines[0] if lines else "Результат"
            body = lines[1:] if len(lines) > 1 else [response_text]
            card = _card(title.rstrip(":"), "\U0001f916", body)
            await update.message.reply_text(card, parse_mode="HTML")
        else:
            await update.message.reply_text(f"\U0001f916 {response_text}")
    else:
        await update.message.reply_text(
            "\U0001f916 Извините, не удалось обработать запрос. Попробуйте ещё раз или используйте меню."
        )


async def _call_ai_backend(message: str, chat_id: int) -> Optional[str]:
    """Call the AI backend endpoint."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                AI_BACKEND_URL,
                json={"message": message, "chat_id": chat_id},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")
            else:
                logger.error(f"AI backend returned {response.status_code}: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error calling AI backend: {e}")
        # Fallback: try direct Groq call
        return await _direct_groq_call(message)


async def _direct_groq_call(message: str) -> Optional[str]:
    """Fallback: call Groq directly if backend is unavailable."""
    try:
        from backend.ai.intents import classify_intent, Intent
        from backend.ai.groq_client import chat_completion
        from backend.ai.knowledge import get_knowledge_context
    except ImportError:
        logger.warning("backend.ai modules not available - AI service unavailable")
        return "AI-сервис недоступен. Используйте команды меню для работы с ботом."

    try:
        intent, params, confidence = await classify_intent(message)

        if intent == Intent.calculate_salary and params.get("oklad"):
            from kindergarten_accountant_bot.handlers.salary import calculate_salary
            result = calculate_salary(
                float(params.get("oklad", 0)),
                float(params.get("rate", 1.0)),
                float(params.get("stazh_percent", 0)),
                float(params.get("category_percent", 0)),
            )
            return (
                f"Расчёт зарплаты:\n"
                f"Начислено: {result['nachisleno']:,.2f} руб.\n"
                f"НДФЛ: {result['ndfl']:,.2f} руб.\n"
                f"На руки: {result['na_ruki']:,.2f} руб."
            )

        elif intent == Intent.calculate_vacation and params.get("total_12_months"):
            from kindergarten_accountant_bot.handlers.vacation import calculate_vacation
            result = calculate_vacation(
                float(params["total_12_months"]),
                int(params.get("days", 14)),
            )
            return (
                f"Расчёт отпускных:\n"
                f"Начислено: {result['vacation_gross']:,.2f} руб.\n"
                f"НДФЛ: {result['ndfl']:,.2f} руб.\n"
                f"На руки: {result['vacation_net']:,.2f} руб."
            )

        elif intent == Intent.calculate_sick and params.get("earnings_2y"):
            from kindergarten_accountant_bot.handlers.sick import calculate_sick
            result = calculate_sick(
                float(params["earnings_2y"]),
                str(params.get("stazh_bracket", ">8")),
                int(params.get("days", 1)),
            )
            return (
                f"Расчёт больничного:\n"
                f"Начислено: {result['total_gross']:,.2f} руб.\n"
                f"НДФЛ: {result['ndfl']:,.2f} руб.\n"
                f"На руки: {result['total_net']:,.2f} руб."
            )

        elif intent == Intent.ask_question:
            knowledge = get_knowledge_context()
            messages = [
                {"role": "system", "content": f"Ты бухгалтер детского сада. Отвечай кратко.\n{knowledge}"},
                {"role": "user", "content": message},
            ]
            return await chat_completion(messages, temperature=0.3)

        else:
            return None

    except Exception as e:
        logger.error(f"Direct Groq call failed: {e}")
        return None
