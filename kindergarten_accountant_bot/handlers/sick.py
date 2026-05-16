from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.config import NDFL_RATE
from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.utils.formatting import _card, format_money
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button

STAZH, EARNINGS, DAYS = range(3)


def calculate_sick(earnings_2y: float, stazh_bracket: str, days: int) -> dict:
    """Calculate sick leave pay. Returns dict with all computed values."""
    if stazh_bracket == "<5":
        percent = 0.60
    elif stazh_bracket == "5-8":
        percent = 0.80
    else:
        percent = 1.00

    daily = (earnings_2y / 730) * percent
    total_gross = daily * days
    ndfl = total_gross * NDFL_RATE
    total_net = total_gross - ndfl

    return {
        "stazh_bracket": stazh_bracket,
        "percent": percent,
        "earnings_2y": earnings_2y,
        "daily": daily,
        "days": days,
        "total_gross": total_gross,
        "ndfl": ndfl,
        "total_net": total_net,
    }


async def sick_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: ask for stazh bracket."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("< 5 лет (60%)", callback_data="sick_stazh_<5"),
            InlineKeyboardButton("5-8 лет (80%)", callback_data="sick_stazh_5-8"),
            InlineKeyboardButton("> 8 лет (100%)", callback_data="sick_stazh_>8"),
        ]
    ]
    await query.edit_message_text(
        "Выберите стаж работы:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STAZH


async def stazh_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle stazh bracket selection, ask for earnings."""
    query = update.callback_query
    await query.answer()
    bracket = query.data.replace("sick_stazh_", "")
    context.user_data["sick_stazh"] = bracket
    await query.edit_message_text(
        "Введите общий заработок за 2 года (сумму):"
    )
    return EARNINGS


async def earnings_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive earnings, ask for sick days."""
    try:
        earnings = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число:")
        return EARNINGS
    context.user_data["sick_earnings"] = earnings
    await update.message.reply_text("Введите количество дней больничного:")
    return DAYS


async def days_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive days, calculate and show result."""
    try:
        days = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите целое число дней:")
        return DAYS

    earnings = context.user_data["sick_earnings"]
    bracket = context.user_data["sick_stazh"]
    result = calculate_sick(earnings, bracket, days)

    bracket_display = {
        "<5": "< 5 лет",
        "5-8": "5-8 лет",
        ">8": "> 8 лет",
    }

    body_lines = [
        f"Стаж:             {bracket_display.get(bracket, bracket)}",
        f"Процент:          {int(result['percent'] * 100)}%",
        f"Заработок 2г:     {format_money(result['earnings_2y'])}",
        f"Дневная ставка:   {format_money(result['daily'])}",
        f"Дней больн.:      {days}",
        "\u2501" * 24,
        f"Начислено:        {format_money(result['total_gross'])}",
        f"НДФЛ (13%):       {format_money(result['ndfl'])}",
        "\u2501" * 24,
        f"\U0001f4b5 На руки:       {format_money(result['total_net'])}",
    ]

    card = _card("Расчёт больничного", "\U0001fa7a", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


sick_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(sick_entry, pattern="^menu_sick$")],
    states={
        STAZH: [CallbackQueryHandler(stazh_selected, pattern=r"^sick_stazh_")],
        EARNINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, earnings_received)],
        DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, days_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)
