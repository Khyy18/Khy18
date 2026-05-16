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

from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.models.employee import (
    add_employee,
    delete_employee,
    get_employee,
    get_employees,
)
from kindergarten_accountant_bot.models.timesheet import (
    add_mark,
    get_monthly_summary,
)
from kindergarten_accountant_bot.utils.constants import MARK_EMOJIS, MARK_TYPES
from kindergarten_accountant_bot.utils.formatting import _card
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button
from kindergarten_accountant_bot.utils.pagination import paginate_items

# Conversation states for add employee
ADD_FIO, ADD_POSITION, ADD_RATE = range(3)

# Conversation states for mark attendance
MARK_SELECT_EMPLOYEE, MARK_SELECT_DATE, MARK_SELECT_TYPE = range(10, 13)

# Conversation states for monthly summary
SUMMARY_SELECT_EMPLOYEE = 20

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


async def timesheet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show timesheet sub-menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Добавить сотрудника", callback_data="ts_add_employee")],
        [InlineKeyboardButton("Список сотрудников", callback_data="ts_list_employees")],
        [InlineKeyboardButton("Отметить посещение", callback_data="ts_mark")],
        [InlineKeyboardButton("Итоги за месяц", callback_data="ts_summary")],
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")],
    ]
    await query.edit_message_text(
        "<b>Табель учёта рабочего времени</b>\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# --- Add Employee conversation ---


async def add_employee_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add employee flow."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите ФИО сотрудника:")
    return ADD_FIO


async def add_employee_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive FIO, ask for position."""
    context.user_data["ts_fio"] = update.message.text.strip()
    await update.message.reply_text("Введите должность:")
    return ADD_POSITION


async def add_employee_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive position, ask for rate."""
    context.user_data["ts_position"] = update.message.text.strip()
    keyboard = [
        [
            InlineKeyboardButton("0.25", callback_data="ts_rate_0.25"),
            InlineKeyboardButton("0.5", callback_data="ts_rate_0.5"),
            InlineKeyboardButton("0.75", callback_data="ts_rate_0.75"),
            InlineKeyboardButton("1.0", callback_data="ts_rate_1.0"),
        ]
    ]
    await update.message.reply_text(
        "Выберите ставку:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADD_RATE


async def add_employee_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive rate, save employee."""
    query = update.callback_query
    await query.answer()
    rate = float(query.data.replace("ts_rate_", ""))
    fio = context.user_data["ts_fio"]
    position = context.user_data["ts_position"]
    emp_id = await add_employee(fio, position, rate)

    body_lines = [
        f"ID:        {emp_id}",
        f"ФИО:       {fio}",
        f"Должность: {position}",
        f"Ставка:    {rate}",
    ]
    card = _card("Сотрудник добавлен", "\u2705", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- List Employees ---


async def list_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show employee list with delete buttons (paginated)."""
    query = update.callback_query
    await query.answer()
    employees = await get_employees()
    if not employees:
        await query.edit_message_text(
            "Список сотрудников пуст.",
            reply_markup=back_to_menu_button(),
        )
        return
    page = context.user_data.get("page_ts_list_page", 0)
    await _show_employees_page(query, context, employees, page)


async def _show_employees_page(query, context, employees, page):
    """Render a specific page of the employee list."""
    context.user_data["page_ts_list_page"] = page
    page_items, nav_buttons = paginate_items(
        employees, page, page_size=5, callback_prefix="page_ts_list"
    )
    keyboard = []
    for emp in page_items:
        keyboard.append(
            [InlineKeyboardButton(
                f"\u274c {emp['fio']} ({emp['position']})",
                callback_data=f"ts_del_{emp['id']}",
            )]
        )
    keyboard.extend(nav_buttons)
    keyboard.append([InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")])
    await query.edit_message_text(
        "<b>Сотрудники</b>\n\nНажмите для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def paginate_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination callback for employee list."""
    query = update.callback_query
    await query.answer()
    page_str = query.data.replace("page_ts_list_", "")
    if page_str == "noop":
        return
    page = int(page_str)
    employees = await get_employees()
    if not employees:
        await query.edit_message_text(
            "Список сотрудников пуст.",
            reply_markup=back_to_menu_button(),
        )
        return
    await _show_employees_page(query, context, employees, page)


async def delete_employee_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle employee deletion."""
    query = update.callback_query
    await query.answer()
    emp_id = int(query.data.replace("ts_del_", ""))
    emp = await get_employee(emp_id)
    deleted = await delete_employee(emp_id)
    if deleted and emp:
        text = f"\u2705 Сотрудник {emp['fio']} удалён."
    else:
        text = "\u274c Сотрудник не найден."
    await query.edit_message_text(
        text,
        reply_markup=back_to_menu_button(),
    )


# --- Mark Attendance conversation ---


async def mark_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start mark attendance flow: show employee list."""
    query = update.callback_query
    await query.answer()
    employees = await get_employees()
    if not employees:
        await query.edit_message_text(
            "Нет сотрудников. Сначала добавьте сотрудника.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END
    keyboard = []
    for emp in employees:
        keyboard.append(
            [InlineKeyboardButton(emp["fio"], callback_data=f"ts_mark_emp_{emp['id']}")]
        )
    await query.edit_message_text(
        "Выберите сотрудника:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MARK_SELECT_EMPLOYEE


async def mark_select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Employee selected, ask for date."""
    query = update.callback_query
    await query.answer()
    emp_id = int(query.data.replace("ts_mark_emp_", ""))
    context.user_data["ts_mark_emp_id"] = emp_id
    today = date.today().strftime("%Y-%m-%d")
    await query.edit_message_text(
        f"Введите дату (ГГГГ-ММ-ДД) или нажмите кнопку для сегодня ({today}):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"Сегодня ({today})", callback_data=f"ts_mark_date_{today}")]]
        ),
    )
    return MARK_SELECT_DATE


async def mark_select_date_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Date selected via button."""
    query = update.callback_query
    await query.answer()
    selected_date = query.data.replace("ts_mark_date_", "")
    context.user_data["ts_mark_date"] = selected_date
    return await _show_mark_type_buttons(query)


async def mark_select_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Date entered via text."""
    text = update.message.text.strip()
    context.user_data["ts_mark_date"] = text
    keyboard = []
    row = []
    for mark_code, mark_name in MARK_TYPES.items():
        emoji = MARK_EMOJIS.get(mark_code, "")
        row.append(InlineKeyboardButton(f"{emoji} {mark_code}", callback_data=f"ts_mark_type_{mark_code}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text(
        "Выберите тип отметки:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MARK_SELECT_TYPE


async def _show_mark_type_buttons(query) -> int:
    """Show mark type selection buttons."""
    keyboard = []
    row = []
    for mark_code, mark_name in MARK_TYPES.items():
        emoji = MARK_EMOJIS.get(mark_code, "")
        row.append(InlineKeyboardButton(f"{emoji} {mark_code}", callback_data=f"ts_mark_type_{mark_code}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await query.edit_message_text(
        "Выберите тип отметки:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return MARK_SELECT_TYPE


async def mark_select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mark type selected, save."""
    query = update.callback_query
    await query.answer()
    mark_type = query.data.replace("ts_mark_type_", "")
    emp_id = context.user_data["ts_mark_emp_id"]
    mark_date = context.user_data["ts_mark_date"]
    await add_mark(emp_id, mark_date, mark_type)
    emp = await get_employee(emp_id)
    fio = emp["fio"] if emp else "?"
    emoji = MARK_EMOJIS.get(mark_type, "")
    mark_name = MARK_TYPES.get(mark_type, mark_type)

    body_lines = [
        f"Сотрудник: {fio}",
        f"Дата:      {mark_date}",
        f"Отметка:   {emoji} {mark_name}",
    ]
    card = _card("Отметка сохранена", "\u2705", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- Monthly Summary conversation ---


async def summary_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start summary flow: show employee list."""
    query = update.callback_query
    await query.answer()
    employees = await get_employees()
    if not employees:
        await query.edit_message_text(
            "Нет сотрудников.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END
    keyboard = []
    for emp in employees:
        keyboard.append(
            [InlineKeyboardButton(emp["fio"], callback_data=f"ts_sum_emp_{emp['id']}")]
        )
    await query.edit_message_text(
        "Выберите сотрудника для просмотра итогов:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SUMMARY_SELECT_EMPLOYEE


async def summary_select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Employee selected, show summary for current month."""
    query = update.callback_query
    await query.answer()
    emp_id = int(query.data.replace("ts_sum_emp_", ""))
    today = date.today()
    year = today.year
    month = today.month
    emp = await get_employee(emp_id)
    fio = emp["fio"] if emp else "?"
    summary = await get_monthly_summary(emp_id, year, month)
    month_name = MONTH_NAMES.get(month, str(month))

    body_lines = [
        f"Месяц: {month_name} {year}",
        "\u2501" * 24,
    ]
    total = 0
    for mark_code, mark_name in MARK_TYPES.items():
        emoji = MARK_EMOJIS.get(mark_code, "")
        count = summary.get(mark_code, 0)
        total += count
        body_lines.append(f"{emoji} {mark_name}:{' ' * (12 - len(mark_name))}{count:>3} дн.")
    body_lines.append("\u2501" * 24)
    body_lines.append(f"Всего отмечено:{' ' * 3}{total:>3} дн.")

    card = _card(f"Табель: {fio}", "\U0001f4cb", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- Handler registration ---

add_employee_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_employee_start, pattern="^ts_add_employee$")],
    states={
        ADD_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_employee_fio)],
        ADD_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_employee_position)],
        ADD_RATE: [CallbackQueryHandler(add_employee_rate, pattern=r"^ts_rate_")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

mark_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(mark_start, pattern="^ts_mark$")],
    states={
        MARK_SELECT_EMPLOYEE: [
            CallbackQueryHandler(mark_select_employee, pattern=r"^ts_mark_emp_\d+$")
        ],
        MARK_SELECT_DATE: [
            CallbackQueryHandler(mark_select_date_button, pattern=r"^ts_mark_date_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, mark_select_date_text),
        ],
        MARK_SELECT_TYPE: [
            CallbackQueryHandler(mark_select_type, pattern=r"^ts_mark_type_")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

summary_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(summary_start, pattern="^ts_summary$")],
    states={
        SUMMARY_SELECT_EMPLOYEE: [
            CallbackQueryHandler(summary_select_employee, pattern=r"^ts_sum_emp_\d+$")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

timesheet_handler = [
    CallbackQueryHandler(timesheet_menu, pattern="^menu_timesheet$"),
    add_employee_conv,
    CallbackQueryHandler(list_employees, pattern="^ts_list_employees$"),
    CallbackQueryHandler(paginate_employees, pattern=r"^page_ts_list_"),
    CallbackQueryHandler(delete_employee_handler, pattern=r"^ts_del_\d+$"),
    mark_conv,
    summary_conv,
]
