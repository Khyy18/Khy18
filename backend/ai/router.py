"""FastAPI router for AI chat endpoint."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.ai.intents import Intent, classify_intent
from backend.ai.groq_client import chat_completion
from backend.ai.knowledge import get_knowledge_context
from backend.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

# Conversation history storage (in-memory, per chat_id)
_conversation_history: dict = {}
HISTORY_MAX_MESSAGES = 5
HISTORY_TIMEOUT_MINUTES = 30
MAX_CONVERSATIONS = 1000


class ChatRequest(BaseModel):
    """Request body for the AI chat endpoint."""
    message: str = Field(..., min_length=1, max_length=2000)
    chat_id: int = Field(default=0)
    history: Optional[List[dict]] = Field(default=None, description="Previous conversation messages")


class ChatResponse(BaseModel):
    """Response body for the AI chat endpoint."""
    response: str
    intent: str
    params: Dict


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def ai_chat(request: Request, data: ChatRequest) -> ChatResponse:
    """Process a natural language message through the AI pipeline.

    Rate limited to 10/minute via the shared app-level limiter.

    Flow:
    1. Retrieve conversation history for chat_id
    2. Classify user message into intent + extract params via Groq LLM
    3. Call the appropriate function based on intent
    4. Format and return the result
    5. Store conversation history
    """
    # Retrieve conversation history
    history = _get_history(data.chat_id)

    intent, params, confidence = await classify_intent(data.message, history=history)

    if intent is None or confidence < 0.3:
        response = ChatResponse(
            response="Не удалось определить ваш запрос. Пожалуйста, уточните, что вы хотите сделать. "
                     "Я могу рассчитать зарплату, отпускные, больничный, найти КБК или ответить на вопрос по бухгалтерии.",
            intent="unknown",
            params=params,
        )
        _update_history(data.chat_id, data.message, response.response)
        return response

    # Execute the intent
    result = await _execute_intent(intent, params, data.message, history=history)
    _update_history(data.chat_id, data.message, result.response)
    return result


async def _execute_intent(
    intent: Intent, params: Dict, original_message: str, history: Optional[List[dict]] = None
) -> ChatResponse:
    """Execute the classified intent and return formatted result."""
    try:
        if intent == Intent.calculate_salary:
            return _handle_salary(params)
        elif intent == Intent.calculate_vacation:
            return _handle_vacation(params)
        elif intent == Intent.calculate_sick:
            return _handle_sick(params)
        elif intent == Intent.search_kbk:
            return await _handle_kbk_search(params)
        elif intent == Intent.ask_question:
            return await _handle_question(params, original_message, history=history)
        elif intent == Intent.generate_text:
            return await _handle_generate_text(params, original_message, history=history)
        elif intent in (Intent.add_employee, Intent.mark_timesheet, Intent.add_journal_entry):
            return ChatResponse(
                response=f"Операция '{intent.value}' принята. Параметры: {params}. "
                         "Для выполнения используйте соответствующий раздел меню бота.",
                intent=intent.value,
                params=params,
            )
        else:
            return await _handle_question(params, original_message, history=history)
    except Exception as e:
        logger.error(f"Error executing intent {intent}: {e}")
        return ChatResponse(
            response=f"Произошла ошибка при выполнении запроса: {str(e)}",
            intent=intent.value if intent else "error",
            params=params,
        )


def _handle_salary(params: Dict) -> ChatResponse:
    """Calculate salary using the same logic as the bot handler."""
    from kindergarten_accountant_bot.handlers.salary import calculate_salary

    oklad = float(params.get("oklad", 0))
    rate = float(params.get("rate", 1.0))
    stazh_percent = float(params.get("stazh_percent", 0))
    category_percent = float(params.get("category_percent", 0))

    if oklad <= 0:
        return ChatResponse(
            response="Для расчёта зарплаты укажите оклад (положительное число).",
            intent=Intent.calculate_salary.value,
            params=params,
        )

    result = calculate_salary(oklad, rate, stazh_percent, category_percent)

    response_text = (
        f"Расчёт заработной платы:\n"
        f"- Оклад: {oklad:,.2f} руб.\n"
        f"- Ставка: {rate}\n"
        f"- Надбавка за стаж: {stazh_percent}%\n"
        f"- Надбавка за категорию: {category_percent}%\n\n"
        f"Начислено: {result['nachisleno']:,.2f} руб.\n"
        f"НДФЛ (13%): {result['ndfl']:,.2f} руб.\n"
        f"На руки: {result['na_ruki']:,.2f} руб.\n\n"
        f"Взносы работодателя:\n"
        f"- ПФР (22%): {result['pfr']:,.2f} руб.\n"
        f"- ОМС (5.1%): {result['oms']:,.2f} руб.\n"
        f"- ФСС (2.9%): {result['fss']:,.2f} руб.\n"
        f"- ФСС НС (0.2%): {result['fss_ns']:,.2f} руб.\n"
        f"- Итого взносов: {result['total_contributions']:,.2f} руб."
    )

    return ChatResponse(
        response=response_text,
        intent=Intent.calculate_salary.value,
        params=params,
    )


def _handle_vacation(params: Dict) -> ChatResponse:
    """Calculate vacation pay using the same logic as the bot handler."""
    from kindergarten_accountant_bot.handlers.vacation import calculate_vacation

    total_12_months = float(params.get("total_12_months", 0))
    days = int(params.get("days", 0))

    if total_12_months <= 0 or days <= 0:
        return ChatResponse(
            response="Для расчёта отпускных укажите общий доход за 12 месяцев и количество дней отпуска.",
            intent=Intent.calculate_vacation.value,
            params=params,
        )

    result = calculate_vacation(total_12_months, days)

    response_text = (
        f"Расчёт отпускных:\n"
        f"- Доход за 12 месяцев: {result['total_12_months']:,.2f} руб.\n"
        f"- Среднемесячный: {result['avg_monthly']:,.2f} руб.\n"
        f"- Среднедневной: {result['avg_daily']:,.2f} руб.\n"
        f"- Дней отпуска: {days}\n\n"
        f"Начислено: {result['vacation_gross']:,.2f} руб.\n"
        f"НДФЛ (13%): {result['ndfl']:,.2f} руб.\n"
        f"На руки: {result['vacation_net']:,.2f} руб."
    )

    return ChatResponse(
        response=response_text,
        intent=Intent.calculate_vacation.value,
        params=params,
    )


def _handle_sick(params: Dict) -> ChatResponse:
    """Calculate sick leave pay using the same logic as the bot handler."""
    from kindergarten_accountant_bot.handlers.sick import calculate_sick

    earnings_2y = float(params.get("earnings_2y", 0))
    stazh_bracket = str(params.get("stazh_bracket", ">8"))
    days = int(params.get("days", 0))

    if earnings_2y <= 0 or days <= 0:
        return ChatResponse(
            response="Для расчёта больничного укажите доход за 2 года, стаж и количество дней.",
            intent=Intent.calculate_sick.value,
            params=params,
        )

    result = calculate_sick(earnings_2y, stazh_bracket, days)

    percent_display = int(result['percent'] * 100)
    response_text = (
        f"Расчёт больничного листа:\n"
        f"- Доход за 2 года: {result['earnings_2y']:,.2f} руб.\n"
        f"- Стаж: {stazh_bracket} лет ({percent_display}%)\n"
        f"- Дневное пособие: {result['daily']:,.2f} руб.\n"
        f"- Дней больничного: {days}\n\n"
        f"Начислено: {result['total_gross']:,.2f} руб.\n"
        f"НДФЛ (13%): {result['ndfl']:,.2f} руб.\n"
        f"На руки: {result['total_net']:,.2f} руб."
    )

    return ChatResponse(
        response=response_text,
        intent=Intent.calculate_sick.value,
        params=params,
    )


async def _handle_kbk_search(params: Dict) -> ChatResponse:
    """Search KBK codes."""
    from kindergarten_accountant_bot.data.kbk_codes import KBK_CODES

    query = str(params.get("query", "")).lower()
    if not query:
        return ChatResponse(
            response="Укажите, какой КБК вы ищете (например, 'НДФЛ', 'страховые взносы').",
            intent=Intent.search_kbk.value,
            params=params,
        )

    results = []
    for code in KBK_CODES:
        name = code.get("name", "")
        description = code.get("description", "")
        if query in name.lower() or query in description.lower():
            results.append(f"- {code.get('code', '')}: {name}")

    if results:
        response_text = f"Найденные КБК по запросу '{query}':\n" + "\n".join(results[:10])
    else:
        response_text = f"КБК по запросу '{query}' не найдены. Попробуйте другие ключевые слова."

    return ChatResponse(
        response=response_text,
        intent=Intent.search_kbk.value,
        params=params,
    )


async def _handle_question(
    params: Dict, original_message: str, history: Optional[List[dict]] = None
) -> ChatResponse:
    """Answer accounting questions using Groq LLM with knowledge context."""
    knowledge = get_knowledge_context()
    question = params.get("question", original_message)

    messages = [
        {
            "role": "system",
            "content": (
                "Ты - опытный бухгалтер детского сада. Отвечай кратко и по делу на русском языке. "
                "Используй следующую справочную информацию:\n\n" + knowledge
            ),
        },
    ]
    # Include conversation history for multi-turn context
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    answer = await chat_completion(messages, temperature=0.3)
    if not answer:
        answer = "Извините, не удалось получить ответ. Попробуйте переформулировать вопрос."

    return ChatResponse(
        response=answer,
        intent=Intent.ask_question.value,
        params=params,
    )


async def _handle_generate_text(
    params: Dict, original_message: str, history: Optional[List[dict]] = None
) -> ChatResponse:
    """Generate text documents using Groq LLM."""
    text_type = params.get("text_type", "документ")
    context_info = params.get("context", original_message)

    messages = [
        {
            "role": "system",
            "content": (
                "Ты - помощник бухгалтера детского сада. "
                "Составь официальный документ по запросу. "
                "Используй деловой стиль русского языка."
            ),
        },
    ]
    # Include conversation history for multi-turn context
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": f"Составь {text_type}: {context_info}"})

    answer = await chat_completion(messages, temperature=0.4, max_tokens=2048)
    if not answer:
        answer = "Извините, не удалось сгенерировать текст. Попробуйте уточнить запрос."

    return ChatResponse(
        response=answer,
        intent=Intent.generate_text.value,
        params=params,
    )


def _get_history(chat_id: int) -> list:
    """Retrieve conversation history for a chat_id, clearing if expired."""
    if chat_id not in _conversation_history:
        return []
    entry = _conversation_history[chat_id]
    if datetime.now() - entry["last_activity"] > timedelta(minutes=HISTORY_TIMEOUT_MINUTES):
        del _conversation_history[chat_id]
        return []
    return entry["messages"]


def _update_history(chat_id: int, user_msg: str, ai_response: str):
    """Store user message and AI response in conversation history."""
    if chat_id == 0:
        return
    if chat_id not in _conversation_history:
        _conversation_history[chat_id] = {"messages": [], "last_activity": datetime.now()}
    entry = _conversation_history[chat_id]
    entry["messages"].append({"role": "user", "content": user_msg})
    entry["messages"].append({"role": "assistant", "content": ai_response})
    # Keep only last N message pairs (N*2 items)
    if len(entry["messages"]) > HISTORY_MAX_MESSAGES * 2:
        entry["messages"] = entry["messages"][-(HISTORY_MAX_MESSAGES * 2):]
    entry["last_activity"] = datetime.now()
    # Evict oldest conversations if exceeding max cap
    if len(_conversation_history) > MAX_CONVERSATIONS:
        oldest_key = min(
            _conversation_history,
            key=lambda k: _conversation_history[k]["last_activity"],
        )
        del _conversation_history[oldest_key]
