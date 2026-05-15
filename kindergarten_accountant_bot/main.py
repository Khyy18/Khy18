from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from kindergarten_accountant_bot.config import BOT_TOKEN
from kindergarten_accountant_bot.models.database import init_db
from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.handlers.start import start_command, main_menu_callback
from kindergarten_accountant_bot.handlers.salary import salary_conv_handler
from kindergarten_accountant_bot.handlers.vacation import vacation_conv_handler
from kindergarten_accountant_bot.handlers.sick import sick_conv_handler
from kindergarten_accountant_bot.handlers.timesheet import timesheet_handler
from kindergarten_accountant_bot.handlers.parents import parents_handler
from kindergarten_accountant_bot.handlers.reminders import reminders_handler, setup_reminder_jobs
from kindergarten_accountant_bot.handlers.kbk import kbk_handler
from kindergarten_accountant_bot.handlers.payment import payment_conv_handler
from kindergarten_accountant_bot.handlers.journal import journal_handler
from kindergarten_accountant_bot.handlers.ai_handler import ai_command, ai_message_handler
from kindergarten_accountant_bot.handlers.payroll import payroll_handler


async def post_init(application):
    await init_db()


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(salary_conv_handler)
    app.add_handler(vacation_conv_handler)
    app.add_handler(sick_conv_handler)
    app.add_handler(payment_conv_handler)
    for handler in timesheet_handler:
        app.add_handler(handler)
    for handler in parents_handler:
        app.add_handler(handler)
    for handler in reminders_handler:
        app.add_handler(handler)
    for handler in kbk_handler:
        app.add_handler(handler)
    for handler in journal_handler:
        app.add_handler(handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^back_to_menu$"))
    app.add_handler(payroll_handler)
    app.add_handler(CommandHandler("ai", ai_command))
    # AI free-text handler - placed last as fallback for unhandled text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_message_handler))
    setup_reminder_jobs(app)
    app.run_polling()


if __name__ == "__main__":
    main()
