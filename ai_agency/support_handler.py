"""AI Live-Support: FAQ + LLM fallback with admin escalation."""

import logging
from typing import Optional, Tuple

import config

# Graceful imports
try:
    import llm_router
except ImportError:
    llm_router = None

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

logger = logging.getLogger(__name__)

# FAQ knowledge base
FAQ_BASE: dict = {
    "что за бот": (
        "Это AI-агентство для автоматизации текстового контента. "
        "Мы делаем копирайтинг, рерайт, SEO-тексты, переводы и другие текстовые услуги "
        "с помощью искусственного интеллекта. Быстро, качественно, недорого."
    ),
    "как платить": (
        "Оплата через YooKassa (карты, SBP) или Telegram Stars. "
        "Пополните баланс через кнопку 'Пополнить' в меню бота, "
        "затем оформляйте заказы. Также доступны подписки BASIC и PRO."
    ),
    "какие гарантии": (
        "Гарантия возврата денег: если результат не устроил, оценка 1-2 звезды - "
        "средства возвращаются на баланс автоматически. "
        "Также предлагаем бесплатную переделку заказа."
    ),
    "сроки выполнения": (
        "Стандартный заказ выполняется за 1-5 минут (AI-генерация). "
        "Срочные заказы обрабатываются приоритетно. "
        "Время может увеличиться при высокой нагрузке."
    ),
    "как отменить": (
        "Заказ можно отменить до начала обработки командой /cancel. "
        "Если заказ уже обработан, но не устроил - поставьте низкую оценку "
        "и средства вернутся на баланс."
    ),
    "как связаться": (
        "Напишите ваш вопрос прямо в этот чат - AI-поддержка ответит мгновенно. "
        "Если вопрос сложный, он будет передан администратору. "
        "Также можно написать @admin напрямую."
    ),
}

# Question starters (Russian)
_QUESTION_STARTERS = ("как", "что", "почему", "сколько", "когда", "где", "можно")

# Uncertainty markers in AI responses
_UNCERTAINTY_MARKERS = ("не уверен", "возможно", "не знаю", "не могу точно", "затрудняюсь")


def detect_question(text: str) -> bool:
    """Return True if text looks like a question (at least 3 words to avoid false positives)."""
    if not text:
        return False
    text_stripped = text.strip()
    # Require minimum length: at least 3 words to avoid triggering on "Что" or "Как"
    words = text_stripped.split()
    if len(words) < 3:
        return False
    if "?" in text_stripped:
        return True
    text_lower = text_stripped.lower()
    for starter in _QUESTION_STARTERS:
        if text_lower.startswith(starter):
            return True
    return False


async def answer_question(text: str, user_context: Optional[dict] = None) -> Tuple[str, bool]:
    """
    Answer a user question.

    Returns (answer_text, is_confident).
    First checks FAQ (fuzzy keyword match), then falls back to LLM generation.
    """
    text_lower = text.lower().strip()

    # Check FAQ by keyword matching
    for keyword, answer in FAQ_BASE.items():
        # Simple fuzzy: check if any keyword word appears in the question
        keyword_words = keyword.split()
        matches = sum(1 for w in keyword_words if w in text_lower)
        if matches >= len(keyword_words) * 0.5:
            return answer, True

    # Not in FAQ - generate via LLM
    answer = await _generate_answer(text, user_context)
    if answer:
        is_confident = not any(marker in answer.lower() for marker in _UNCERTAINTY_MARKERS)
        return answer, is_confident

    return "К сожалению, я не могу ответить на этот вопрос. Передаю администратору.", False


async def _generate_answer(text: str, user_context: Optional[dict] = None) -> Optional[str]:
    """Generate answer via LLM router or direct OpenAI."""
    system_prompt = (
        "Ты - AI-поддержка текстового агентства. Отвечай кратко, по делу, на русском языке. "
        "Если не знаешь ответа - честно скажи об этом."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    if user_context:
        context_str = ", ".join(f"{k}: {v}" for k, v in user_context.items())
        messages.insert(1, {"role": "system", "content": f"Контекст клиента: {context_str}"})

    # Try llm_router first
    if llm_router:
        try:
            result = await llm_router.generate(messages, temperature=0.7, max_tokens=300)
            if result:
                return result
        except Exception as e:
            logger.warning("LLM router failed for support: %s", e)

    # Fallback to direct OpenAI
    if AsyncOpenAI and config.OPENAI_API_KEY:
        try:
            client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=300,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning("OpenAI fallback failed for support: %s", e)

    return None


async def handle_support_message(update, context) -> None:
    """
    Handle a support message from the bot fallback handler.

    If detect_question returns True, get answer. If not confident, escalate to admin.
    """
    text = update.message.text
    if not text:
        return

    if not detect_question(text):
        return

    user = update.effective_user
    user_context = {"telegram_id": user.id, "username": user.username or ""}

    answer, is_confident = await answer_question(text, user_context)

    # Send answer to user
    await update.message.reply_text(answer)

    # If not confident, escalate to admin
    if not is_confident and config.ADMIN_TELEGRAM_ID:
        try:
            admin_msg = (
                f"[Support Escalation]\n"
                f"User: {user.first_name} (@{user.username}, ID: {user.id})\n"
                f"Question: {text}\n"
                f"AI Answer: {answer}"
            )
            await context.bot.send_message(
                chat_id=config.ADMIN_TELEGRAM_ID,
                text=admin_msg,
            )
        except Exception as e:
            logger.warning("Failed to notify admin about support escalation: %s", e)
