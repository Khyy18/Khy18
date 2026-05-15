from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from kindergarten_accountant_bot.config import BOT_TOKEN
from kindergarten_accountant_bot.models.database import init_db
from kindergarten_accountant_bot.handlers.start import start_command, main_menu_callback


async def post_init(application):
    await init_db()


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^back_to_menu$"))
    # Other handlers will be registered here
    app.run_polling()


if __name__ == "__main__":
    main()
