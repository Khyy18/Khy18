from telegram import Update
from telegram.ext import ContextTypes

from kindergarten_accountant_bot.utils.keyboards import main_menu_keyboard


WELCOME_TEXT = (
    "<b>Добро пожаловать!</b>\n\n"
    "Я - бот-помощник главного бухгалтера детского сада.\n"
    "Выберите нужный раздел:"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - send welcome message with main menu."""
    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back_to_menu callback - edit message to show main menu."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
