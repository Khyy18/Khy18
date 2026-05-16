from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.config import BASE_FEE_PER_DAY
from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.models.child import (
    add_child,
    delete_child,
    get_child,
    get_children,
)
from kindergarten_accountant_bot.models.payment import (
    create_fee_record,
    get_debts,
    get_payment_record,
    record_payment,
)
from kindergarten_accountant_bot.utils.formatting import _card, format_money
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button
from kindergarten_accountant_bot.utils.pagination import paginate_items

# Conversation states for add child
ADD_CHILD_FIO, ADD_CHILD_GROUP, ADD_CHILD_PARENT, ADD_CHILD_DISCOUNT = range(4)

# Conversation states for calculate fee
CALC_SELECT_CHILD, CALC_INPUT_DAYS = range(10, 12)

# Conversation states for record payment
PAY_SELECT_CHILD, PAY_INPUT_AMOUNT = range(20, 22)

MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


async def parents_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show parents sub-menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Добавить ребёнка", callback_data="pr_add_child")],
        [InlineKeyboardButton("Список детей", callback_data="pr_list_children")],
        [InlineKeyboardButton("Рассчитать плату", callback_data="pr_calc_fee")],
        [InlineKeyboardButton("Внести оплату", callback_data="pr_record_payment")],
        [InlineKeyboardButton("Отчёт по задолженности", callback_data="pr_debt_report")],
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")],
    ]
    await query.edit_message_text(
        "<b>Родительская плата</b>\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# --- Add Child conversation ---


async def add_child_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add child flow."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ФИО ребёнка:")
    return ADD_CHILD_FIO


async def add_child_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive child FIO, ask for group."""
    context.user_data["pr_child_fio"] = update.message.text.strip()
    await update.message.reply_text("Введите название группы:")
    return ADD_CHILD_GROUP


async def add_child_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive group, ask for parent FIO."""
    context.user_data["pr_group"] = update.message.text.strip()
    await update.message.reply_text("Введите ФИО родителя:")
    return ADD_CHILD_PARENT


async def add_child_parent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive parent FIO, ask for discount."""
    context.user_data["pr_parent_fio"] = update.message.text.strip()
    await update.message.reply_text(
        "Введите процент льготы (0 если нет, например 50 для 50%):"
    )
    return ADD_CHILD_DISCOUNT


async def add_child_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive discount, save child."""
    try:
        discount = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число. Попробуйте ещё раз:")
        return ADD_CHILD_DISCOUNT

    child_fio = context.user_data["pr_child_fio"]
    group = context.user_data["pr_group"]
    parent_fio = context.user_data["pr_parent_fio"]
    child_id = await add_child(child_fio, group, parent_fio, discount)

    body_lines = [
        f"ID:       {child_id}",
        f"Ребёнок:  {child_fio}",
        f"Группа:   {group}",
        f"Родитель: {parent_fio}",
        f"Льгота:   {discount:.0f}%",
    ]
    card = _card("Ребёнок добавлен", "\u2705", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- List Children ---


async def list_children_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show children list with delete buttons (paginated)."""
    query = update.callback_query
    await query.answer()
    children = await get_children()
    if not children:
        await query.edit_message_text(
            "Список детей пуст.",
            reply_markup=back_to_menu_button(),
        )
        return
    page = context.user_data.get("page_pr_list_page", 0)
    await _show_children_page(query, context, children, page)


async def _show_children_page(query, context, children, page):
    """Render a specific page of the children list."""
    context.user_data["page_pr_list_page"] = page
    page_items, nav_buttons = paginate_items(
        children, page, page_size=5, callback_prefix="page_pr_list"
    )
    keyboard = []
    for child in page_items:
        keyboard.append(
            [InlineKeyboardButton(
                f"\u274c {child['child_fio']} ({child['group_name']})",
                callback_data=f"pr_del_{child['id']}",
            )]
        )
    keyboard.extend(nav_buttons)
    keyboard.append([InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")])
    await query.edit_message_text(
        "<b>Дети</b>\n\nНажмите для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def paginate_children(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination callback for children list."""
    query = update.callback_query
    await query.answer()
    page_str = query.data.replace("page_pr_list_", "")
    if page_str == "noop":
        return
    page = int(page_str)
    children = await get_children()
    if not children:
        await query.edit_message_text(
            "Список детей пуст.",
            reply_markup=back_to_menu_button(),
        )
        return
    await _show_children_page(query, context, children, page)


async def delete_child_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle child deletion."""
    query = update.callback_query
    await query.answer()
    child_id = int(query.data.replace("pr_del_", ""))
    child = await get_child(child_id)
    deleted = await delete_child(child_id)
    if deleted and child:
        text = f"\u2705 Ребёнок {child['child_fio']} удалён."
    else:
        text = "\u274c Ребёнок не найден."
    await query.edit_message_text(
        text,
        reply_markup=back_to_menu_button(),
    )


# --- Calculate Fee conversation ---


async def calc_fee_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start fee calculation: show child list."""
    query = update.callback_query
    await query.answer()
    children = await get_children()
    if not children:
        await query.edit_message_text(
            "Нет детей. Сначала добавьте ребёнка.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END
    keyboard = []
    for child in children:
        keyboard.append(
            [InlineKeyboardButton(
                f"{child['child_fio']} ({child['group_name']})",
                callback_data=f"pr_calc_child_{child['id']}",
            )]
        )
    await query.edit_message_text(
        "Выберите ребёнка для расчёта:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CALC_SELECT_CHILD


async def calc_select_child(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Child selected, ask for attendance days."""
    query = update.callback_query
    await query.answer()
    child_id = int(query.data.replace("pr_calc_child_", ""))
    context.user_data["pr_calc_child_id"] = child_id
    await query.edit_message_text("Введите количество дней посещения:")
    return CALC_INPUT_DAYS


async def calc_input_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive days, calculate and show fee."""
    try:
        days = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите целое число. Попробуйте ещё раз:")
        return CALC_INPUT_DAYS

    child_id = context.user_data["pr_calc_child_id"]
    child = await get_child(child_id)
    if not child:
        await update.message.reply_text(
            "Ребёнок не найден.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END

    discount = child["discount_percent"]
    fee = BASE_FEE_PER_DAY * days * (1 - discount / 100)
    today = date.today()
    month = today.month
    year = today.year
    month_name = MONTH_NAMES.get(month, str(month))

    await create_fee_record(child_id, month, year, days, fee)

    body_lines = [
        f"Ребёнок: {child['child_fio']}",
        f"Группа:  {child['group_name']}",
        f"Месяц:   {month_name} {year}",
        "\u2501" * 24,
        f"Дней посещения:  {days}",
        f"Тариф/день:     {format_money(BASE_FEE_PER_DAY)}",
        f"Льгота:         {discount:.0f}%",
        "\u2501" * 24,
        f"К оплате:     {format_money(fee)}",
    ]
    card = _card("Расчёт родительской платы", "\U0001f9d2", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- Record Payment conversation ---


async def pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start payment recording: show child list."""
    query = update.callback_query
    await query.answer()
    children = await get_children()
    if not children:
        await query.edit_message_text(
            "Нет детей.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END
    keyboard = []
    for child in children:
        keyboard.append(
            [InlineKeyboardButton(
                f"{child['child_fio']} ({child['group_name']})",
                callback_data=f"pr_pay_child_{child['id']}",
            )]
        )
    await query.edit_message_text(
        "Выберите ребёнка для внесения оплаты:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return PAY_SELECT_CHILD


async def pay_select_child(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Child selected, show current due and ask for amount."""
    query = update.callback_query
    await query.answer()
    child_id = int(query.data.replace("pr_pay_child_", ""))
    context.user_data["pr_pay_child_id"] = child_id

    today = date.today()
    record = await get_payment_record(child_id, today.month, today.year)
    if record:
        due = record["amount_due"]
        paid = record["amount_paid"]
        remaining = due - paid
        text = (
            f"К оплате: {format_money(due)}\n"
            f"Оплачено: {format_money(paid)}\n"
            f"Остаток:  {format_money(remaining)}\n\n"
            "Введите сумму оплаты:"
        )
    else:
        text = "Нет начислений за текущий месяц.\nВведите сумму оплаты:"

    await query.edit_message_text(text)
    return PAY_INPUT_AMOUNT


async def pay_input_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive payment amount, save."""
    try:
        amount = float(update.message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число. Попробуйте ещё раз:")
        return PAY_INPUT_AMOUNT
    if amount <= 0:
        await update.message.reply_text("Введите положительное число")
        return PAY_INPUT_AMOUNT

    child_id = context.user_data["pr_pay_child_id"]
    today = date.today()
    updated = await record_payment(child_id, today.month, today.year, amount)
    if not updated:
        await update.message.reply_text(
            "Нет начислений за текущий месяц. Сначала рассчитайте плату.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END
    child = await get_child(child_id)
    child_fio = child["child_fio"] if child else "?"

    body_lines = [
        f"Ребёнок: {child_fio}",
        f"Сумма:   {format_money(amount)}",
        f"Дата:    {today.strftime('%d.%m.%Y')}",
    ]
    card = _card("Оплата внесена", "\u2705", body_lines)
    await update.message.reply_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- Debt Report ---


async def debt_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show debt report (paginated)."""
    query = update.callback_query
    await query.answer()
    debts = await get_debts()
    if not debts:
        await query.edit_message_text(
            "\u2705 Задолженностей нет!",
            reply_markup=back_to_menu_button(),
        )
        return
    page = context.user_data.get("page_pr_debt_page", 0)
    await _show_debt_page(query, context, debts, page)


async def _show_debt_page(query, context, debts, page):
    """Render a specific page of the debt report."""
    context.user_data["page_pr_debt_page"] = page
    page_items, nav_buttons = paginate_items(
        debts, page, page_size=5, callback_prefix="page_pr_debt"
    )

    body_lines = []
    for record in page_items:
        due = record["amount_due"]
        paid = record["amount_paid"]
        remaining = due - paid
        if paid == 0:
            indicator = "\U0001f534"
        elif paid < due:
            indicator = "\U0001f7e1"
        else:
            indicator = "\U0001f7e2"
        month_name = MONTH_NAMES.get(record["month"], str(record["month"]))
        body_lines.append(
            f"{indicator} {record['child_fio']} ({month_name}): {format_money(remaining)}"
        )

    card = _card("Отчёт по задолженности", "\U0001f4cb", body_lines)

    # Build keyboard with nav buttons and back to menu
    keyboard = []
    keyboard.extend(nav_buttons)
    keyboard.append([InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")])
    await query.edit_message_text(
        card,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def paginate_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination callback for debt report."""
    query = update.callback_query
    await query.answer()
    page_str = query.data.replace("page_pr_debt_", "")
    if page_str == "noop":
        return
    page = int(page_str)
    debts = await get_debts()
    if not debts:
        await query.edit_message_text(
            "\u2705 Задолженностей нет!",
            reply_markup=back_to_menu_button(),
        )
        return
    await _show_debt_page(query, context, debts, page)


# --- Handler registration ---

add_child_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_child_start, pattern="^pr_add_child$")],
    states={
        ADD_CHILD_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_child_fio)],
        ADD_CHILD_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_child_group)],
        ADD_CHILD_PARENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_child_parent)],
        ADD_CHILD_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_child_discount)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

calc_fee_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(calc_fee_start, pattern="^pr_calc_fee$")],
    states={
        CALC_SELECT_CHILD: [
            CallbackQueryHandler(calc_select_child, pattern=r"^pr_calc_child_\d+$")
        ],
        CALC_INPUT_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, calc_input_days)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

pay_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(pay_start, pattern="^pr_record_payment$")],
    states={
        PAY_SELECT_CHILD: [
            CallbackQueryHandler(pay_select_child, pattern=r"^pr_pay_child_\d+$")
        ],
        PAY_INPUT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_input_amount)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

parents_handler = [
    CallbackQueryHandler(parents_menu, pattern="^menu_parents$"),
    add_child_conv,
    CallbackQueryHandler(list_children_handler, pattern="^pr_list_children$"),
    CallbackQueryHandler(paginate_children, pattern=r"^page_pr_list_"),
    CallbackQueryHandler(delete_child_handler, pattern=r"^pr_del_\d+$"),
    calc_fee_conv,
    pay_conv,
    CallbackQueryHandler(debt_report, pattern="^pr_debt_report$"),
    CallbackQueryHandler(paginate_debt, pattern=r"^page_pr_debt_"),
]
