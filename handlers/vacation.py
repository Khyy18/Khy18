from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.config import AVG_DAYS_MONTH, NDFL_RATE
from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.utils.formatting import _card, format_money
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button

INPUT_MODE, MONTHLY_INPUT, SINGLE_SUM, DAYS = range(4)


def calculate_vacation(total_12_months: float, days: int) -> dict:
    """Calculate vacation pay. Returns dict with all computed values."""
    avg_monthly = total_12_months / 12
    avg_daily = total_12_months / 12 / AVG_DAYS_MONTH
    vacation_gross = avg_daily * days
    ndfl = vacation_gross * NDFL_RATE
    vacation_net = vacation_gross - ndfl
    return {
        "total_12_months": total_12_months,
        "avg_monthly": avg_monthly,
        "avg_daily": avg_daily,
        "days": days,
        "vacation_gross": vacation_gross,
        "ndfl": ndfl,
        "vacation_net": vacation_net,
    }


async def vacation_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: ask for input mode."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("Общая сумма за 12 мес", callback_data="vac_single"),
            InlineKeyboardButton("Помесячно", callback_data="vac_monthly"),
        ]
    ]
    await query.edit_message_text(
        "Как вы хотите ввести доход за 12 месяцев?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return INPUT_MODE


async def input_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle input mode selection."""
    query = update.callback_query
    await query.answer()
    if query.data == "vac_single":
        await query.edit_message_text(
            "Введите общую сумму дохода за 12 месяцев:"
        )
        return SINGLE_SUM
    else:
        await query.edit_message_text(
            "Введите доходы за 12 месяцев через запятую\n"
            "(например: 30000, 30000, 35000, ...):"
        )
        return MONTHLY_INPUT


async def monthly_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive 12 monthly values, sum them, ask for days."""
    text = update.message.text.strip()
    parts = [p.strip() for p in text.replace(",", " ").split() if p.strip()]
    try:
        values = [float(p) for p in parts]
    except ValueError:
        await update.message.reply_text(
            "Не удалось разобрать числа. Введите 12 значений через запятую:"
        )
        return MONTHLY_INPUT
    context.user_data["vacation_total"] = sum(values)
    await update.message.reply_text("Введите количество дней отпуска:")
    return DAYS


async def single_sum_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive single total sum, ask for days."""
    try:
        total = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число:")
        return SINGLE_SUM
    context.user_data["vacation_total"] = total
    await update.message.reply_text("Введите количество дней отпуска:")
    return DAYS


async def days_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive days, calculate and show result."""
    try:
        days = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите целое число дней:")
        return DAYS

    total_12 = context.user_data["vacation_total"]
    result = calculate_vacation(total_12, days)

    body_lines = [
        f"Доход за 12 мес:  {format_money(result['total_12_months'])}",
        f"Ср. мес. доход:   {format_money(result['avg_monthly'])}",
        f"Ср. дневной:      {format_money(result['avg_daily'])}",
        f"Дней отпуска:     {days}",
        "\u2501" * 24,
        f"Начислено:        {format_money(result['vacation_gross'])}",
        f"НДФЛ (13%):       {format_money(result['ndfl'])}",
        "\u2501" * 24,
        f"\U0001f4b5 На руки:       {format_money(result['vacation_net'])}",
    ]

    card = _card("Расчёт отпускных", "\U0001f3d6\ufe0f", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


vacation_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(vacation_entry, pattern="^menu_vacation$")],
    states={
        INPUT_MODE: [CallbackQueryHandler(input_mode_selected, pattern=r"^vac_")],
        MONTHLY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, monthly_input_received)],
        SINGLE_SUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, single_sum_received)],
        DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, days_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)
