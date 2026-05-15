"""Intent definitions and extraction logic for AI classification."""

import json
import logging
from enum import Enum
from typing import Dict, Optional, Tuple

from backend.ai.groq_client import chat_completion
from backend.ai.knowledge import get_knowledge_context

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    """Supported intents for the AI classifier."""
    calculate_salary = "calculate_salary"
    calculate_vacation = "calculate_vacation"
    calculate_sick = "calculate_sick"
    add_employee = "add_employee"
    mark_timesheet = "mark_timesheet"
    add_journal_entry = "add_journal_entry"
    search_kbk = "search_kbk"
    ask_question = "ask_question"
    generate_text = "generate_text"


INTENT_DESCRIPTIONS = {
    Intent.calculate_salary: "Расчёт заработной платы. Параметры: oklad (float), rate (float, 0.25-1.0), stazh_percent (float), category_percent (float, по умолчанию 0)",
    Intent.calculate_vacation: "Расчёт отпускных. Параметры: total_12_months (float - общий доход за 12 месяцев), days (int - дней отпуска)",
    Intent.calculate_sick: "Расчёт больничного листа. Параметры: earnings_2y (float - доход за 2 года), stazh_bracket (str: '<5', '5-8', '>8'), days (int)",
    Intent.add_employee: "Добавление сотрудника. Параметры: name (str), position (str), oklad (float, необязательно)",
    Intent.mark_timesheet: "Отметка в табеле. Параметры: employee_name (str), date (str, YYYY-MM-DD), status (str: present/absent/sick/vacation)",
    Intent.add_journal_entry: "Запись в журнал операций. Параметры: description (str), amount (float), entry_type (str: income/expense)",
    Intent.search_kbk: "Поиск КБК (код бюджетной классификации). Параметры: query (str)",
    Intent.ask_question: "Вопрос по бухгалтерии детского сада. Параметры: question (str)",
    Intent.generate_text: "Генерация текста (приказ, справка, заявление). Параметры: text_type (str), context (str)",
}

SYSTEM_PROMPT = """Ты - AI-ассистент бухгалтера детского сада. Твоя задача - определить намерение пользователя и извлечь параметры из его сообщения.

Доступные намерения (intents):
{intent_list}

Контекст знаний:
{knowledge}

ВАЖНО: Ответь СТРОГО в формате JSON без дополнительного текста:
{{
  "intent": "<название_намерения>",
  "params": {{<параметры>}},
  "confidence": <число от 0 до 1>
}}

Если не можешь определить намерение, верни:
{{
  "intent": "ask_question",
  "params": {{"question": "<исходный текст пользователя>"}},
  "confidence": 0.3
}}

Примеры:
- "Рассчитай зарплату: оклад 30000, ставка 1.0, стаж 10%" -> {{"intent": "calculate_salary", "params": {{"oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 0}}, "confidence": 0.95}}
- "Сколько отпускных за 14 дней если доход 500000?" -> {{"intent": "calculate_vacation", "params": {{"total_12_months": 500000, "days": 14}}, "confidence": 0.9}}
- "Больничный 10 дней, стаж 6 лет, доход за 2 года 800000" -> {{"intent": "calculate_sick", "params": {{"earnings_2y": 800000, "stazh_bracket": "5-8", "days": 10}}, "confidence": 0.9}}
- "Найди КБК для НДФЛ" -> {{"intent": "search_kbk", "params": {{"query": "НДФЛ"}}, "confidence": 0.9}}
- "Какой срок сдачи 6-НДФЛ?" -> {{"intent": "ask_question", "params": {{"question": "Какой срок сдачи 6-НДФЛ?"}}, "confidence": 0.8}}
"""


def _build_system_prompt() -> str:
    """Build the system prompt with intent descriptions and knowledge context."""
    intent_list = "\n".join(
        f"- {intent.value}: {desc}"
        for intent, desc in INTENT_DESCRIPTIONS.items()
    )
    knowledge = get_knowledge_context()
    return SYSTEM_PROMPT.format(intent_list=intent_list, knowledge=knowledge)


async def classify_intent(user_message: str) -> Tuple[Optional[Intent], Dict, float]:
    """Classify user message into an intent with extracted parameters.

    Args:
        user_message: The user's natural language message in Russian.

    Returns:
        Tuple of (Intent or None, params dict, confidence float).
    """
    system_prompt = _build_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = await chat_completion(messages)
    if not response:
        return None, {}, 0.0

    return _parse_classification_response(response)


def _parse_classification_response(response: str) -> Tuple[Optional[Intent], Dict, float]:
    """Parse the LLM response into intent, params, and confidence.

    Args:
        response: Raw LLM response string (expected JSON).

    Returns:
        Tuple of (Intent or None, params dict, confidence float).
    """
    try:
        # Strip any markdown code block markers
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)
        intent_str = data.get("intent", "")
        params = data.get("params", {})
        confidence = float(data.get("confidence", 0.0))

        try:
            intent = Intent(intent_str)
        except ValueError:
            logger.warning(f"Unknown intent from LLM: {intent_str}")
            return None, params, confidence

        return intent, params, confidence

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse LLM classification response: {e}, response: {response[:200]}")
        return None, {}, 0.0
