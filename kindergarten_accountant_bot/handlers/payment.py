"""Handlers for payment order generation."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.data.kbk_codes import POPULAR_KBK
from kindergarten_accountant_bot.utils.formatting import _card, format_money
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button

# Conversation states
RECIPIENT, INN, KPP, ACCOUNT, BIK, AMOUNT, PURPOSE, KBK_INPUT = range(8)


async def payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start payment order: ask recipient name."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите наименование получателя:")
    return RECIPIENT


async def payment_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive recipient name, ask for INN."""
    context.user_data["pay_recipient"] = update.message.text.strip()
    await update.message.reply_text("Введите ИНН получателя (10 или 12 цифр):")
    return INN


async def payment_inn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive INN, validate, ask for KPP."""
    inn = update.message.text.strip().replace(" ", "")
    if not inn.isdigit() or len(inn) not in (10, 12):
        await update.message.reply_text(
            "ИНН должен содержать 10 или 12 цифр. Попробуйте ещё раз:"
        )
        return INN
    context.user_data["pay_inn"] = inn
    keyboard = [[InlineKeyboardButton("Пропустить", callback_data="pay_skip_kpp")]]
    await update.message.reply_text(
        "Введите КПП (9 цифр) или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return KPP


async def payment_kpp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive KPP, validate, ask for account."""
    kpp = update.message.text.strip().replace(" ", "")
    if not kpp.isdigit() or len(kpp) != 9:
        await update.message.reply_text(
            "КПП должен содержать 9 цифр. Попробуйте ещё раз:"
        )
        return KPP
    context.user_data["pay_kpp"] = kpp
    await update.message.reply_text("Введите расчётный счёт (20 цифр):")
    return ACCOUNT


async def payment_skip_kpp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip KPP entry."""
    query = update.callback_query
    await query.answer()
    context.user_data["pay_kpp"] = "-"
    await query.edit_message_text("Введите расчётный счёт (20 цифр):")
    return ACCOUNT


async def payment_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive account, validate, ask for BIK."""
    account = update.message.text.strip().replace(" ", "")
    if not account.isdigit() or len(account) != 20:
        await update.message.reply_text(
            "Расчётный счёт должен содержать 20 цифр. Попробуйте ещё раз:"
        )
        return ACCOUNT
    context.user_data["pay_account"] = account
    await update.message.reply_text("Введите БИК (9 цифр):")
    return BIK


async def payment_bik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive BIK, validate, ask for amount."""
    bik = update.message.text.strip().replace(" ", "")
    if not bik.isdigit() or len(bik) != 9:
        await update.message.reply_text(
            "БИК должен содержать 9 цифр. Попробуйте ещё раз:"
        )
        return BIK
    context.user_data["pay_bik"] = bik
    await update.message.reply_text("Введите сумму платежа:")
    return AMOUNT


async def payment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive amount, ask for purpose."""
    text = update.message.text.strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(text)
    except ValueError:
        await update.message.reply_text("Введите число. Попробуйте ещё раз:")
        return AMOUNT
    context.user_data["pay_amount"] = amount
    await update.message.reply_text("Введите назначение платежа:")
    return PURPOSE


async def payment_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive purpose, ask for KBK."""
    context.user_data["pay_purpose"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("Выбрать из справочника", callback_data="pay_kbk_ref")]
    ]
    await update.message.reply_text(
        "Введите КБК или выберите из справочника:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return KBK_INPUT


async def payment_kbk_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive KBK manually typed."""
    context.user_data["pay_kbk"] = update.message.text.strip()
    return await _generate_payment_order(update, context, via_message=True)


async def payment_kbk_from_ref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show popular KBK codes for selection."""
    query = update.callback_query
    await query.answer()
    keyboard = []
    for entry in POPULAR_KBK[:10]:
        keyboard.append(
            [InlineKeyboardButton(
                f"{entry['short_name']}",
                callback_data=f"pay_kbk_sel_{entry['code']}",
            )]
        )
    await query.edit_message_text(
        "Выберите КБК:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return KBK_INPUT


async def payment_kbk_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle KBK selected from reference."""
    query = update.callback_query
    await query.answer()
    kbk = query.data.replace("pay_kbk_sel_", "")
    context.user_data["pay_kbk"] = kbk
    return await _generate_payment_order_from_callback(update, context)


async def _generate_payment_order(update: Update, context: ContextTypes.DEFAULT_TYPE, via_message=True) -> int:
    """Generate and show formatted payment order."""
    data = context.user_data
    body_lines = [
        f"Получатель: {data['pay_recipient']}",
        f"ИНН: {data['pay_inn']}",
        f"КПП: {data['pay_kpp']}",
        f"Р/сч: {data['pay_account']}",
        f"БИК: {data['pay_bik']}",
        "\u2501" * 24,
        f"Сумма: {format_money(data['pay_amount'])}",
        "\u2501" * 24,
        f"Назначение: {data['pay_purpose']}",
        f"КБК: {data['pay_kbk']}",
    ]
    card = _card("Платёжное поручение", "\U0001f4c4", body_lines)
    if via_message:
        await update.message.reply_text(
            card,
            reply_markup=back_to_menu_button(),
            parse_mode="HTML",
        )
    return ConversationHandler.END


async def _generate_payment_order_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate payment order from callback query context."""
    data = context.user_data
    body_lines = [
        f"Получатель: {data['pay_recipient']}",
        f"ИНН: {data['pay_inn']}",
        f"КПП: {data['pay_kpp']}",
        f"Р/сч: {data['pay_account']}",
        f"БИК: {data['pay_bik']}",
        "\u2501" * 24,
        f"Сумма: {format_money(data['pay_amount'])}",
        "\u2501" * 24,
        f"Назначение: {data['pay_purpose']}",
        f"КБК: {data['pay_kbk']}",
    ]
    card = _card("Платёжное поручение", "\U0001f4c4", body_lines)
    query = update.callback_query
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


payment_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(payment_menu, pattern="^menu_payment$")],
    states={
        RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_recipient)],
        INN: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_inn)],
        KPP: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, payment_kpp),
            CallbackQueryHandler(payment_skip_kpp, pattern="^pay_skip_kpp$"),
        ],
        ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_account)],
        BIK: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_bik)],
        AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_amount)],
        PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_purpose)],
        KBK_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, payment_kbk_input),
            CallbackQueryHandler(payment_kbk_from_ref, pattern="^pay_kbk_ref$"),
            CallbackQueryHandler(payment_kbk_selected, pattern="^pay_kbk_sel_.+$"),
        ],
    },
    fallbacks=[],
)
