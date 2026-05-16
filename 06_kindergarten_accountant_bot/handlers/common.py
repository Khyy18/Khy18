"""Common handlers shared across conversation flows."""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from kindergarten_accountant_bot.utils.keyboards import main_menu_keyboard


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current conversation, clear user_data, and show main menu."""
    context.user_data.clear()
    await update.message.reply_text(
        "Действие отменено. Выберите раздел:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    return ConversationHandler.END
