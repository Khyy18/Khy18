from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from kindergarten_accountant_bot.config import WEBAPP_URL


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return main menu inline keyboard with 9 buttons in 3 rows of 3."""
    keyboard = [
        [
            InlineKeyboardButton("Зарплата", callback_data="menu_salary"),
            InlineKeyboardButton("Отпускные", callback_data="menu_vacation"),
            InlineKeyboardButton("Больничный", callback_data="menu_sick"),
        ],
        [
            InlineKeyboardButton("Табель", callback_data="menu_timesheet"),
            InlineKeyboardButton("Род. плата", callback_data="menu_parents"),
            InlineKeyboardButton("Напоминания", callback_data="menu_reminders"),
        ],
        [
            InlineKeyboardButton("КБК/КВР", callback_data="menu_kbk"),
            InlineKeyboardButton("Плат. поручение", callback_data="menu_payment"),
            InlineKeyboardButton("Журнал", callback_data="menu_journal"),
        ],
        [
            InlineKeyboardButton("\U0001f4ca Ведомость", callback_data="menu_payroll"),
        ],
    ]
    if WEBAPP_URL:
        keyboard.append([
            InlineKeyboardButton(
                "\U0001f4f1 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL),
            ),
        ])
    return InlineKeyboardMarkup(keyboard)


def back_to_menu_button() -> InlineKeyboardMarkup:
    """Return single button to go back to main menu."""
    keyboard = [[InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")]]
    return InlineKeyboardMarkup(keyboard)
