from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.config import (
    FSS_NS_RATE,
    FSS_RATE,
    NDFL_RATE,
    OMS_RATE,
    PFR_RATE,
)
from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.utils.formatting import _card, format_money
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button

OKLAD, RATE, STAZH, CATEGORY = range(4)


def calculate_salary(oklad: float, rate: float, stazh_percent: float, category_percent: float = 0) -> dict:
    """Calculate salary breakdown. Returns dict with all computed values."""
    nachisleno = oklad * rate * (1 + stazh_percent / 100 + category_percent / 100)
    ndfl = nachisleno * NDFL_RATE
    pfr = nachisleno * PFR_RATE
    oms = nachisleno * OMS_RATE
    fss = nachisleno * FSS_RATE
    fss_ns = nachisleno * FSS_NS_RATE
    total_contributions = pfr + oms + fss + fss_ns
    na_ruki = nachisleno - ndfl
    return {
        "nachisleno": nachisleno,
        "ndfl": ndfl,
        "pfr": pfr,
        "oms": oms,
        "fss": fss,
        "fss_ns": fss_ns,
        "total_contributions": total_contributions,
        "na_ruki": na_ruki,
    }


async def salary_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: ask for oklad."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите оклад (базовую ставку) числом:",
        parse_mode="HTML",
    )
    return OKLAD


async def oklad_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive oklad, ask for rate."""
    try:
        oklad = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число. Попробуйте ещё раз:")
        return OKLAD
    if oklad <= 0:
        await update.message.reply_text("Введите положительное число")
        return OKLAD
    context.user_data["salary_oklad"] = oklad
    keyboard = [
        [
            InlineKeyboardButton("0.25", callback_data="rate_0.25"),
            InlineKeyboardButton("0.5", callback_data="rate_0.5"),
            InlineKeyboardButton("0.75", callback_data="rate_0.75"),
            InlineKeyboardButton("1.0", callback_data="rate_1.0"),
        ]
    ]
    await update.message.reply_text(
        "Выберите ставку:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return RATE


async def rate_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive rate selection, ask for stazh percent."""
    query = update.callback_query
    await query.answer()
    rate_value = float(query.data.replace("rate_", ""))
    context.user_data["salary_rate"] = rate_value
    await query.edit_message_text(
        "Введите надбавку за стаж в процентах (например, 10 означает 10%).\n"
        "Если нет надбавки, введите 0:"
    )
    return STAZH


async def stazh_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive stazh percent, ask for category bonus."""
    try:
        stazh = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число. Попробуйте ещё раз:")
        return STAZH
    context.user_data["salary_stazh"] = stazh
    await update.message.reply_text(
        "Введите надбавку за категорию в процентах (0, если нет):"
    )
    return CATEGORY


async def category_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive category, calculate and show result."""
    try:
        category_percent = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        category_percent = 0

    oklad = context.user_data["salary_oklad"]
    rate = context.user_data["salary_rate"]
    stazh = context.user_data["salary_stazh"]

    result = calculate_salary(oklad, rate, stazh, category_percent)

    body_lines = [
        f"Оклад:           {format_money(oklad)}",
        f"Ставка:          {rate}",
        f"Надбавка стаж:   {stazh:.0f}%",
        f"Надбавка кат.:   {category_percent:.0f}%",
        "\u2501" * 24,
        f"Начислено:       {format_money(result['nachisleno'])}",
        f"НДФЛ (13%):      {format_money(result['ndfl'])}",
        "\u2501" * 24,
        "Взносы работодателя:",
        f"ПФР (22%):        {format_money(result['pfr'])}",
        f"ОМС (5.1%):      {format_money(result['oms'])}",
        f"ФСС (2.9%):        {format_money(result['fss'])}",
        f"ФСС НС (0.2%):      {format_money(result['fss_ns'])}",
        f"Итого взносов:    {format_money(result['total_contributions'])}",
        "\u2501" * 24,
        f"\U0001f4b5 На руки:      {format_money(result['na_ruki'])}",
    ]

    card = _card("Расчёт заработной платы", "\U0001f4b0", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


salary_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(salary_entry, pattern="^menu_salary$")],
    states={
        OKLAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, oklad_received)],
        RATE: [CallbackQueryHandler(rate_selected, pattern=r"^rate_")],
        STAZH: [MessageHandler(filters.TEXT & ~filters.COMMAND, stazh_received)],
        CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)
