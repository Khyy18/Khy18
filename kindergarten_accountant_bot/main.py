import asyncio
import logging
import os

import sentry_sdk
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from kindergarten_accountant_bot.config import (
    BOT_TOKEN,
    SENTRY_DSN,
    WEBHOOK_URL,
    WEBHOOK_SECRET,
    WEBHOOK_PORT,
)
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
from kindergarten_accountant_bot.handlers.audit import audit_handler
from kindergarten_accountant_bot.handlers.voice_handler import voice_message_handler
from kindergarten_accountant_bot.handlers.backup_handler import backup_command, setup_backup_jobs

# Initialize Sentry if DSN is configured
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1)


async def post_init(application):
    await init_db()


def _build_application() -> Application:
    """Build the Application and register all handlers."""
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
    app.add_handler(audit_handler)
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("backup", backup_command))
    # Voice handler - before text fallback
    app.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    # AI free-text handler - placed last as fallback for unhandled text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_message_handler))
    setup_reminder_jobs(app)
    setup_backup_jobs(app)
    return app


async def _run_webhook(application: Application) -> None:
    """Run the bot in webhook mode using aiohttp."""
    from aiohttp import web

    await application.initialize()
    await application.bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}",
        secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
    )
    await application.start()

    async def handle_webhook(request: web.Request) -> web.Response:
        """Handle incoming Telegram webhook update."""
        # Validate secret token if configured
        if WEBHOOK_SECRET:
            header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header_token != WEBHOOK_SECRET:
                return web.Response(status=403, text="Forbidden")

        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(status=200, text="OK")

    webapp = web.Application()
    webapp.router.add_post(f"/webhook/{BOT_TOKEN}", handle_webhook)

    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()

    # Keep running until interrupted
    try:
        await asyncio.Event().wait()
    finally:
        await application.stop()
        await application.shutdown()
        await runner.cleanup()


def main():
    app = _build_application()

    if WEBHOOK_URL:
        # Webhook mode
        if not WEBHOOK_SECRET:
            logging.warning(
                "WARNING: Webhook запущен без WEBHOOK_SECRET - "
                "входящие обновления не аутентифицируются"
            )
        asyncio.run(_run_webhook(app))
    else:
        # Polling mode (default, unchanged behavior)
        app.run_polling()


if __name__ == "__main__":
    main()
