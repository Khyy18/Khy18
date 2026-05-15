"""Интернационализация (i18n) для AI-агентства: RU и EN строки."""

from typing import Dict, Tuple

# Словарь текстов: (язык, ключ) -> шаблон строки
TEXTS: Dict[Tuple[str, str], str] = {
    # --- Welcome ---
    ("ru", "welcome"): "Привет, <b>{name}</b>! Я AI-агентство для работы с текстами.",
    ("en", "welcome"): "Hello, <b>{name}</b>! I am an AI text agency.",

    # --- Free trial ---
    ("ru", "first_order_free"): "\U0001f381 Первый заказ БЕСПЛАТНО!",
    ("en", "first_order_free"): "\U0001f381 First order FREE!",

    # --- Confirm order ---
    ("ru", "confirm_order"): "Подтвердите заказ:",
    ("en", "confirm_order"): "Confirm your order:",

    # --- Insufficient funds ---
    ("ru", "insufficient_funds"): "Недостаточно средств. Пополните баланс или оформите подписку.",
    ("en", "insufficient_funds"): "Insufficient funds. Top up your balance or subscribe.",

    # --- Order processing ---
    ("ru", "order_processing"): "Обработка заказа...",
    ("en", "order_processing"): "Processing your order...",

    # --- Order completed ---
    ("ru", "order_completed"): "Заказ выполнен!",
    ("en", "order_completed"): "Order completed!",

    # --- Order failed ---
    ("ru", "order_failed"): "Произошла ошибка при обработке. Средства возвращены на баланс.",
    ("en", "order_failed"): "An error occurred during processing. Funds have been refunded.",

    # --- Rate prompt ---
    ("ru", "rate_prompt"): "\U0001f4dd Оцените результат:",
    ("en", "rate_prompt"): "\U0001f4dd Rate the result:",

    # --- Service list ---
    ("ru", "service_list"): "Выбери услугу из списка ниже:",
    ("en", "service_list"): "Choose a service from the list below:",

    # --- Balance ---
    ("ru", "balance"): "Ваш баланс: {amount} \u20bd",
    ("en", "balance"): "Your balance: {amount} \u20bd",

    # --- Top up ---
    ("ru", "topup"): "Пополнение баланса",
    ("en", "topup"): "Top up balance",

    # --- Subscriptions ---
    ("ru", "subscriptions"): "Подписки",
    ("en", "subscriptions"): "Subscriptions",

    # --- Referral ---
    ("ru", "referral"): "Реферальная программа",
    ("en", "referral"): "Referral program",

    # --- My orders ---
    ("ru", "my_orders"): "Мои заказы",
    ("en", "my_orders"): "My orders",

    # --- Cancel ---
    ("ru", "cancel"): "Операция отменена. Нажмите /start для начала.",
    ("en", "cancel"): "Operation cancelled. Press /start to begin.",

    # --- Download ---
    ("ru", "download_docx"): "\U0001f4c4 Скачать .docx",
    ("en", "download_docx"): "\U0001f4c4 Download .docx",

    ("ru", "download_pdf"): "\U0001f4d5 Скачать .pdf",
    ("en", "download_pdf"): "\U0001f4d5 Download .pdf",

    # --- Urgency prompt ---
    ("ru", "urgency_prompt"): "Выберите срочность заказа:",
    ("en", "urgency_prompt"): "Select order urgency:",

    # --- Price calculated ---
    ("ru", "price_calculated"): "Рассчитанная стоимость: {price} \u20bd",
    ("en", "price_calculated"): "Calculated price: {price} \u20bd",

    # --- Trial used ---
    ("ru", "trial_used"): "Бесплатный пробный заказ уже использован.",
    ("en", "trial_used"): "Free trial order has already been used.",

    # --- Urgency buttons ---
    ("ru", "urgency_normal"): "\u23f0 Обычный",
    ("en", "urgency_normal"): "\u23f0 Normal",

    ("ru", "urgency_urgent"): "\u26a1 Срочный (x1.5)",
    ("en", "urgency_urgent"): "\u26a1 Urgent (x1.5)",

    # --- Language selection ---
    ("ru", "lang_set"): "Язык установлен: Русский \U0001f1f7\U0001f1fa",
    ("en", "lang_set"): "Language set: English \U0001f1ec\U0001f1e7",

    # --- Persona greeting ---
    ("ru", "persona_greeting"): "{greeting}",
    ("en", "persona_greeting"): "{greeting}",
}


def get_text(lang: str, key: str, **kwargs) -> str:
    """
    Получить локализованный текст.

    Args:
        lang: код языка ('ru' или 'en')
        key: ключ текста
        **kwargs: параметры для .format()

    Returns:
        Отформатированная строка. Если ключ не найден, возвращает RU версию или ключ.
    """
    text = TEXTS.get((lang, key))
    if text is None:
        # Фолбэк на русский
        text = TEXTS.get(("ru", key))
    if text is None:
        return key
    return text.format(**kwargs) if kwargs else text
