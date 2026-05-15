"""Handlers for operations journal."""

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.models.journal import (
    add_entry,
    get_entries_for_period,
    get_totals_for_period,
)
from kindergarten_accountant_bot.utils.formatting import _card, format_money, progress_bar
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button

# Conversation states for add entry
JRN_DATE, JRN_AMOUNT, JRN_TYPE, JRN_COUNTERPARTY, JRN_BASIS = range(5)

# Conversation states for view journal
JRN_VIEW_PERIOD, JRN_VIEW_START, JRN_VIEW_END = range(10, 13)

# Conversation states for totals
JRN_TOTALS_PERIOD, JRN_TOTALS_START, JRN_TOTALS_END = range(20, 23)


def _parse_date(text: str) -> str:
    """Parse date from DD.MM.YYYY or YYYY-MM-DD format. Returns YYYY-MM-DD."""
    text = text.strip()
    if "." in text:
        parts = text.split(".")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return text


async def journal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show journal sub-menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Добавить запись", callback_data="jrn_add")],
        [InlineKeyboardButton("Просмотр журнала", callback_data="jrn_view")],
        [InlineKeyboardButton("Итоги", callback_data="jrn_totals")],
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")],
    ]
    await query.edit_message_text(
        "<b>Журнал операций</b>\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# --- Add Entry conversation ---


async def jrn_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add entry: ask for date."""
    query = update.callback_query
    await query.answer()
    today = date.today().strftime("%d.%m.%Y")
    await query.edit_message_text(
        f"Введите дату операции (ДД.ММ.ГГГГ или ГГГГ-ММ-ДД).\n"
        f"По умолчанию: {today}\n\n"
        f"Отправьте дату или '.' для сегодняшней:"
    )
    return JRN_DATE


async def jrn_add_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive date, ask for amount."""
    text = update.message.text.strip()
    if text == ".":
        context.user_data["jrn_date"] = date.today().strftime("%Y-%m-%d")
    else:
        context.user_data["jrn_date"] = _parse_date(text)
    await update.message.reply_text("Введите сумму:")
    return JRN_AMOUNT


async def jrn_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive amount, ask for type."""
    text = update.message.text.strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(text)
    except ValueError:
        await update.message.reply_text("Введите число. Попробуйте ещё раз:")
        return JRN_AMOUNT
    context.user_data["jrn_amount"] = amount
    keyboard = [
        [
            InlineKeyboardButton("Поступление", callback_data="jrn_type_income"),
            InlineKeyboardButton("Списание", callback_data="jrn_type_expense"),
        ]
    ]
    await update.message.reply_text(
        "Выберите тип операции:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return JRN_TYPE


async def jrn_add_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive type, ask for counterparty."""
    query = update.callback_query
    await query.answer()
    entry_type = "income" if query.data == "jrn_type_income" else "expense"
    context.user_data["jrn_type"] = entry_type
    await query.edit_message_text("Введите контрагента:")
    return JRN_COUNTERPARTY


async def jrn_add_counterparty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive counterparty, ask for basis."""
    context.user_data["jrn_counterparty"] = update.message.text.strip()
    await update.message.reply_text("Введите основание (документ):")
    return JRN_BASIS


async def jrn_add_basis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive basis, save entry."""
    context.user_data["jrn_basis"] = update.message.text.strip()
    data = context.user_data
    entry_id = await add_entry(
        data["jrn_date"],
        data["jrn_amount"],
        data["jrn_type"],
        data["jrn_counterparty"],
        data["jrn_basis"],
    )
    type_label = "Поступление" if data["jrn_type"] == "income" else "Списание"
    body_lines = [
        f"ID:          {entry_id}",
        f"Дата:        {data['jrn_date']}",
        f"Тип:         {type_label}",
        f"Сумма:       {format_money(data['jrn_amount'])}",
        f"Контрагент:  {data['jrn_counterparty']}",
        f"Основание:   {data['jrn_basis']}",
    ]
    card = _card("Запись добавлена", "\u2705", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- View Journal conversation ---


async def jrn_view_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start view: ask for period."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Текущий месяц", callback_data="jrn_vp_current")],
        [InlineKeyboardButton("Прошлый месяц", callback_data="jrn_vp_last")],
        [InlineKeyboardButton("Указать период", callback_data="jrn_vp_custom")],
    ]
    await query.edit_message_text(
        "Выберите период:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return JRN_VIEW_PERIOD


async def jrn_view_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle period selection for view."""
    query = update.callback_query
    await query.answer()
    today = date.today()

    if query.data == "jrn_vp_current":
        start = today.replace(day=1).strftime("%Y-%m-%d")
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end = end_date.strftime("%Y-%m-%d")
        return await _show_journal_entries(query, start, end)
    elif query.data == "jrn_vp_last":
        first_of_current = today.replace(day=1)
        last_month_end = first_of_current - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        start = last_month_start.strftime("%Y-%m-%d")
        end = last_month_end.strftime("%Y-%m-%d")
        return await _show_journal_entries(query, start, end)
    else:
        await query.edit_message_text("Введите дату начала периода (ДД.ММ.ГГГГ):")
        return JRN_VIEW_START


async def jrn_view_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive start date for custom period."""
    context.user_data["jrn_view_start"] = _parse_date(update.message.text)
    await update.message.reply_text("Введите дату окончания периода (ДД.ММ.ГГГГ):")
    return JRN_VIEW_END


async def jrn_view_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive end date and show entries."""
    start = context.user_data["jrn_view_start"]
    end = _parse_date(update.message.text)
    entries = await get_entries_for_period(start, end)

    start_display = _format_display_date(start)
    end_display = _format_display_date(end)

    if not entries:
        await update.message.reply_text(
            f"Нет записей за период {start_display}-{end_display}.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END

    body_lines = [f"Период: {start_display}-{end_display}", ""]
    for e in entries:
        arrow = "\u25b2" if e["entry_type"] == "income" else "\u25bc"
        d = e["date"][8:10] + "." + e["date"][5:7]
        body_lines.append(f"{d} {arrow}  {format_money(e['amount'])}")
        body_lines.append(f"  {e['basis']} \u2014 {e['counterparty']}")
    body_lines.append("")
    body_lines.append(f"Записей: {len(entries)}")

    card = _card("Журнал операций", "\U0001f4d2", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def _show_journal_entries(query, start: str, end: str) -> int:
    """Show journal entries for a period (used by callback handlers)."""
    entries = await get_entries_for_period(start, end)

    start_display = _format_display_date(start)
    end_display = _format_display_date(end)

    if not entries:
        await query.edit_message_text(
            f"Нет записей за период {start_display}-{end_display}.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END

    body_lines = [f"Период: {start_display}-{end_display}", ""]
    for e in entries:
        arrow = "\u25b2" if e["entry_type"] == "income" else "\u25bc"
        d = e["date"][8:10] + "." + e["date"][5:7]
        body_lines.append(f"{d} {arrow}  {format_money(e['amount'])}")
        body_lines.append(f"  {e['basis']} \u2014 {e['counterparty']}")
    body_lines.append("")
    body_lines.append(f"Записей: {len(entries)}")

    card = _card("Журнал операций", "\U0001f4d2", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- Totals conversation ---


async def jrn_totals_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start totals: ask for period."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Текущий месяц", callback_data="jrn_tp_current")],
        [InlineKeyboardButton("Прошлый месяц", callback_data="jrn_tp_last")],
        [InlineKeyboardButton("Указать период", callback_data="jrn_tp_custom")],
    ]
    await query.edit_message_text(
        "Выберите период для итогов:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return JRN_TOTALS_PERIOD


async def jrn_totals_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle period selection for totals."""
    query = update.callback_query
    await query.answer()
    today = date.today()

    if query.data == "jrn_tp_current":
        start = today.replace(day=1).strftime("%Y-%m-%d")
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end = end_date.strftime("%Y-%m-%d")
        return await _show_totals(query, start, end)
    elif query.data == "jrn_tp_last":
        first_of_current = today.replace(day=1)
        last_month_end = first_of_current - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        start = last_month_start.strftime("%Y-%m-%d")
        end = last_month_end.strftime("%Y-%m-%d")
        return await _show_totals(query, start, end)
    else:
        await query.edit_message_text("Введите дату начала периода (ДД.ММ.ГГГГ):")
        return JRN_TOTALS_START


async def jrn_totals_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive start date for custom totals period."""
    context.user_data["jrn_totals_start"] = _parse_date(update.message.text)
    await update.message.reply_text("Введите дату окончания периода (ДД.ММ.ГГГГ):")
    return JRN_TOTALS_END


async def jrn_totals_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive end date and show totals."""
    start = context.user_data["jrn_totals_start"]
    end = _parse_date(update.message.text)
    totals = await get_totals_for_period(start, end)

    start_display = _format_display_date(start)
    end_display = _format_display_date(end)

    income = totals["income"]
    expense = totals["expense"]
    balance = totals["balance"]
    total = income + expense
    ratio = int(income / total * 100) if total > 0 else 0

    body_lines = [
        f"Период: {start_display}-{end_display}",
        "",
        f"\u25b2 Поступления: {format_money(income)}",
        f"\u25bc Списания:    {format_money(expense)}",
        "",
        f"Баланс:        {format_money(balance)}",
        f"[{progress_bar(ratio, 100)}] {ratio}%",
    ]
    card = _card("Итоги за период", "\U0001f4ca", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def _show_totals(query, start: str, end: str) -> int:
    """Show totals for a period (used by callback handlers)."""
    totals = await get_totals_for_period(start, end)

    start_display = _format_display_date(start)
    end_display = _format_display_date(end)

    income = totals["income"]
    expense = totals["expense"]
    balance = totals["balance"]
    total = income + expense
    ratio = int(income / total * 100) if total > 0 else 0

    body_lines = [
        f"Период: {start_display}-{end_display}",
        "",
        f"\u25b2 Поступления: {format_money(income)}",
        f"\u25bc Списания:    {format_money(expense)}",
        "",
        f"Баланс:        {format_money(balance)}",
        f"[{progress_bar(ratio, 100)}] {ratio}%",
    ]
    card = _card("Итоги за период", "\U0001f4ca", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


def _format_display_date(iso_date: str) -> str:
    """Convert YYYY-MM-DD to DD.MM.YYYY for display."""
    parts = iso_date.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return iso_date


# --- Handler registration ---

add_entry_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(jrn_add_start, pattern="^jrn_add$")],
    states={
        JRN_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_add_date)],
        JRN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_add_amount)],
        JRN_TYPE: [
            CallbackQueryHandler(jrn_add_type, pattern="^jrn_type_(income|expense)$")
        ],
        JRN_COUNTERPARTY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_add_counterparty)
        ],
        JRN_BASIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_add_basis)],
    },
    fallbacks=[],
)

view_journal_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(jrn_view_start, pattern="^jrn_view$")],
    states={
        JRN_VIEW_PERIOD: [
            CallbackQueryHandler(jrn_view_period, pattern="^jrn_vp_(current|last|custom)$")
        ],
        JRN_VIEW_START: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_view_start_date)
        ],
        JRN_VIEW_END: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_view_end_date)
        ],
    },
    fallbacks=[],
)

totals_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(jrn_totals_start, pattern="^jrn_totals$")],
    states={
        JRN_TOTALS_PERIOD: [
            CallbackQueryHandler(jrn_totals_period, pattern="^jrn_tp_(current|last|custom)$")
        ],
        JRN_TOTALS_START: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_totals_start_date)
        ],
        JRN_TOTALS_END: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, jrn_totals_end_date)
        ],
    },
    fallbacks=[],
)

journal_handler = [
    CallbackQueryHandler(journal_menu, pattern="^menu_journal$"),
    add_entry_conv,
    view_journal_conv,
    totals_conv,
]
