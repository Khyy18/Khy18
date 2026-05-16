"""Handlers for KBK/KVR reference dictionary."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from kindergarten_accountant_bot.data.kbk_codes import KBK_CODES, POPULAR_KBK, search_kbk
from kindergarten_accountant_bot.handlers.common import cancel
from kindergarten_accountant_bot.utils.formatting import _card
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button

# Conversation states
KBK_SEARCH_INPUT = 0


async def kbk_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show KBK sub-menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Поиск по КБК", callback_data="kbk_search")],
        [InlineKeyboardButton("Популярные КБК", callback_data="kbk_popular")],
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")],
    ]
    await query.edit_message_text(
        "<b>Справочник КБК/КВР</b>\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def kbk_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start search flow: ask for search query."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите поисковый запрос (код, название или ключевое слово):"
    )
    return KBK_SEARCH_INPUT


async def kbk_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process search query and show results."""
    query_text = update.message.text.strip()
    results = search_kbk(query_text)

    if not results:
        await update.message.reply_text(
            f"По запросу \"{query_text}\" ничего не найдено.",
            reply_markup=back_to_menu_button(),
        )
        return ConversationHandler.END

    # Store results for pagination
    context.user_data["kbk_results"] = results
    context.user_data["kbk_page"] = 0
    context.user_data["kbk_query"] = query_text

    text = _format_kbk_results(results[:5], query_text)
    keyboard = []
    if len(results) > 5:
        keyboard.append(
            [InlineKeyboardButton("\u0415\u0449\u0451 \u25b6", callback_data="kbk_next_page")]
        )
    keyboard.append(
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")]
    )
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def kbk_next_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show next page of KBK search results."""
    query = update.callback_query
    await query.answer()

    results = context.user_data.get("kbk_results", [])
    page = context.user_data.get("kbk_page", 0) + 1
    context.user_data["kbk_page"] = page
    query_text = context.user_data.get("kbk_query", "")

    start = page * 5
    end = start + 5
    page_results = results[start:end]

    if not page_results:
        await query.edit_message_text(
            "Больше результатов нет.",
            reply_markup=back_to_menu_button(),
        )
        return

    text = _format_kbk_results(page_results, query_text)
    keyboard = []
    if len(results) > end:
        keyboard.append(
            [InlineKeyboardButton("\u0415\u0449\u0451 \u25b6", callback_data="kbk_next_page")]
        )
    keyboard.append(
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")]
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def kbk_popular_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show popular KBK codes."""
    query = update.callback_query
    await query.answer()

    body_lines = []
    for entry in POPULAR_KBK:
        body_lines.append(f"КБК: {entry['code']}")
        body_lines.append(f"КВР: {entry['kvr']}")
        body_lines.append(f"{entry['short_name']}")
        body_lines.append(f"{entry['description']}")
        body_lines.append("")

    card = _card("Популярные КБК", "\U0001f4da", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )


def _format_kbk_results(results: list, query_text: str) -> str:
    """Format KBK search results as card."""
    body_lines = []
    for entry in results:
        body_lines.append(f"КБК: {entry['code']}")
        body_lines.append(f"КВР: {entry['kvr']}")
        body_lines.append(f"{entry['short_name']}")
        body_lines.append(f"{entry['description']}")
        body_lines.append("")

    return _card(f'Результаты поиска: "{query_text}"', "\U0001f4da", body_lines)


kbk_search_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(kbk_search_start, pattern="^kbk_search$")],
    states={
        KBK_SEARCH_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, kbk_search_input)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=600,
)

kbk_handler = [
    CallbackQueryHandler(kbk_menu, pattern="^menu_kbk$"),
    kbk_search_conv,
    CallbackQueryHandler(kbk_popular_handler, pattern="^kbk_popular$"),
    CallbackQueryHandler(kbk_next_page, pattern="^kbk_next_page$"),
]
