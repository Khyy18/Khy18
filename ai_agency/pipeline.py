"""Пайплайн обработки заказов: мульти-агентная цепочка Writer->Editor->QA с Groq-фолбэком."""

import logging
from typing import Optional, List, Dict, Tuple

from openai import AsyncOpenAI
from groq import AsyncGroq

import config
from models import ServiceType
from services import get_service
import ab_testing

logger = logging.getLogger(__name__)

# Услуги, которые обрабатываются в простом режиме (без Editor/QA)
SIMPLE_SERVICES = {ServiceType.REWRITE, ServiceType.SUMMARY}

# Хранилище variant_id для заказов (ключ: (service_type, input_text_hash))
_last_variant_ids: Dict[int, int] = {}

# Lazy-singleton LLM клиенты (создаются при первом использовании)
_openai_client: Optional[AsyncOpenAI] = None
_groq_client: Optional[AsyncGroq] = None


def _get_openai_client() -> AsyncOpenAI:
    """Получить или создать singleton AsyncOpenAI клиент."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def _get_groq_client() -> Optional[AsyncGroq]:
    """Получить или создать singleton AsyncGroq клиент."""
    global _groq_client
    if not config.GROQ_API_KEY:
        return None
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=config.GROQ_API_KEY)
    return _groq_client


def _check_quality(text: str, min_words: int, required_keywords: list) -> bool:
    """Проверка качества результата."""
    words = text.split()
    if len(words) < min_words:
        return False
    if required_keywords:
        text_lower = text.lower()
        for keyword in required_keywords:
            if keyword.lower() not in text_lower:
                return False
    return True


async def _call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> Optional[str]:
    """
    Вызвать LLM с фолбэком на Groq.

    Сначала пытается OpenAI, при ошибке переключается на Groq.
    Использует singleton-клиенты для переиспользования HTTP-соединений.
    """
    # Попытка через OpenAI
    try:
        client = _get_openai_client()
        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("OpenAI API ошибка, переключение на Groq: %s", str(e))

    # Фолбэк на Groq
    groq_client = _get_groq_client()
    if groq_client is None:
        logger.error("Groq API ключ не задан, фолбэк невозможен")
        return None

    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Groq API ошибка: %s", str(e))
        return None


async def _writer_agent(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Агент-писатель: генерирует первоначальный текст."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return await _call_llm(messages)


async def _editor_agent(text: str) -> Optional[str]:
    """Агент-редактор: улучшает стиль и структуру."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional editor. Improve the text's style, structure, "
                "and readability. Fix any grammatical errors. Keep the same language "
                "as the input text. Do not change the meaning or key information. "
                "Return only the improved text without explanations."
            ),
        },
        {
            "role": "user",
            "content": f"Отредактируй и улучши следующий текст:\n\n{text}",
        },
    ]
    return await _call_llm(messages, temperature=0.4)


async def _qa_agent(original_task: str, text: str) -> Optional[str]:
    """Агент QA: проверяет на ошибки и соответствие заданию."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a QA reviewer. Check the text for errors, factual accuracy, "
                "and compliance with the original task. If the text is good, return it "
                "as-is. If there are issues, fix them and return the corrected version. "
                "Keep the same language. Return only the final text without explanations."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Задание:\n{original_task}\n\n"
                f"Текст для проверки:\n{text}\n\n"
                "Проверь текст на ошибки и соответствие заданию. "
                "Верни исправленную версию."
            ),
        },
    ]
    return await _call_llm(messages, temperature=0.3)


async def process_order(service_type: ServiceType, input_text: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Обработать заказ через мульти-агентную цепочку.

    Полный режим (Writer -> Editor -> QA):
    - Используется для большинства услуг

    Простой режим (только Writer):
    - Для rewrite и summary (дешевле, быстрее)

    При неудаче проверки качества повторяет Writer один раз.

    Возвращает (result_text, variant_id). variant_id = None если A/B тест не использовался.
    """
    service = get_service(service_type)
    quality = service.quality_checks
    simple_mode = service_type in SIMPLE_SERVICES

    # A/B тестирование: пробуем получить вариант промпта
    variant_id = None
    system_prompt = service.system_prompt
    try:
        variant = await ab_testing.select_variant(service_type.value)
        if variant:
            variant_id, system_prompt = variant
    except Exception as e:
        logger.warning("Ошибка A/B тестирования: %s", e)

    user_prompt = service.user_prompt_template.format(input_text=input_text)
    max_attempts = quality.max_retry + 1

    for attempt in range(max_attempts):
        # 1. Writer agent
        result_text = await _writer_agent(system_prompt, user_prompt)
        if not result_text:
            if attempt < max_attempts - 1:
                continue
            return (None, variant_id)

        # Простой режим - пропускаем Editor и QA
        if simple_mode:
            if _check_quality(result_text, quality.min_words, quality.required_keywords):
                return (result_text, variant_id)
            if attempt < max_attempts - 1:
                logger.warning(
                    "Проверка качества не пройдена для %s (простой режим), попытка %d/%d",
                    service_type.value, attempt + 1, max_attempts,
                )
                user_prompt = (
                    f"{user_prompt}\n\nПредыдущий результат был недостаточно подробным. "
                    f"Расширь ответ, минимум {quality.min_words} слов."
                )
                continue
            return (result_text, variant_id)

        # 2. Editor agent
        edited_text = await _editor_agent(result_text)
        if not edited_text:
            edited_text = result_text  # используем текст писателя если редактор упал

        # 3. QA agent
        final_text = await _qa_agent(input_text, edited_text)
        if not final_text:
            final_text = edited_text  # используем текст редактора если QA упал

        # Проверка качества
        if _check_quality(final_text, quality.min_words, quality.required_keywords):
            return (final_text, variant_id)

        if attempt < max_attempts - 1:
            logger.warning(
                "Проверка качества не пройдена для %s, попытка %d/%d",
                service_type.value, attempt + 1, max_attempts,
            )
            user_prompt = (
                f"{user_prompt}\n\nПредыдущий результат был недостаточно подробным. "
                f"Расширь ответ, минимум {quality.min_words} слов."
            )
        else:
            return (final_text, variant_id)

    return (None, variant_id)
