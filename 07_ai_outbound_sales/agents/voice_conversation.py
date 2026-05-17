"""Voice Conversation Agent - manages AI-powered voice call conversations."""

from __future__ import annotations

import enum
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.llm import LLMClient

logger = logging.getLogger(__name__)


class ConversationState(str, enum.Enum):
    greeting = "greeting"
    qualification = "qualification"
    offer = "offer"
    objection_handling = "objection_handling"
    closing = "closing"
    ended = "ended"


VOICE_SYSTEM_PROMPT = """\
You are an AI voice sales assistant making outbound calls on behalf of a company.
Your goal is to have a natural, professional phone conversation that qualifies the prospect and advances toward a meeting or sale.

Guidelines:
- Speak naturally and conversationally, as if on a real phone call
- Keep responses concise (1-3 sentences max for voice delivery)
- Be empathetic and listen actively
- Never be pushy or aggressive
- If the prospect is not interested, be gracious and end the call politely

{personality_instructions}

Lead context:
- Name: {lead_name}
- Company: {lead_company}
- Title: {lead_title}

{script_instructions}

{conversation_context}

Current conversation state: {state}

Based on the conversation state:
- greeting: Introduce yourself warmly and state the reason for calling
- qualification: Ask qualifying questions to understand their needs
- offer: Present the value proposition tailored to their situation
- objection_handling: Address concerns empathetically with relevant benefits
- closing: Summarize value and suggest next steps (meeting, demo, etc.)

Return your response as a JSON object with these fields:
- response_text: Your spoken response (keep it natural and brief)
- new_state: The next conversation state based on how the conversation is progressing

Only return the JSON object, no other text.
"""

# Multi-language system prompts
VOICE_SYSTEM_PROMPTS: dict[str, str] = {
    "en": VOICE_SYSTEM_PROMPT,
    "ru": """\
Вы AI голосовой помощник по продажам, совершающий исходящие звонки от имени компании.
Ваша цель - вести естественный, профессиональный телефонный разговор, который квалифицирует потенциального клиента и продвигает к встрече или продаже.

Рекомендации:
- Говорите естественно и разговорно, как в настоящем телефонном разговоре
- Отвечайте кратко (1-3 предложения максимум)
- Будьте эмпатичны и слушайте внимательно
- Никогда не давите и не будьте агрессивны
- Если потенциальный клиент не заинтересован, завершите разговор вежливо

{personality_instructions}

Контекст лида:
- Имя: {lead_name}
- Компания: {lead_company}
- Должность: {lead_title}

{script_instructions}

{conversation_context}

Текущее состояние разговора: {state}

На основе состояния разговора:
- greeting: Представьтесь и объясните причину звонка
- qualification: Задайте квалификационные вопросы
- offer: Представьте ценностное предложение
- objection_handling: Обработайте возражения
- closing: Подведите итог и предложите следующие шаги

Верните ответ как JSON объект с полями:
- response_text: Ваш устный ответ (кратко и естественно)
- new_state: Следующее состояние разговора

Верните только JSON объект, никакого другого текста.
""",
    "es": """\
Eres un asistente de ventas por voz con IA que realiza llamadas salientes en nombre de una empresa.
Tu objetivo es tener una conversacion telefonica natural y profesional que califique al prospecto y avance hacia una reunion o venta.

Pautas:
- Habla de forma natural y conversacional, como en una llamada telefonica real
- Mantén las respuestas concisas (1-3 oraciones como maximo)
- Se empatico y escucha activamente
- Nunca seas insistente o agresivo
- Si el prospecto no esta interesado, se amable y termina la llamada cortesmente

{personality_instructions}

Contexto del lead:
- Nombre: {lead_name}
- Empresa: {lead_company}
- Cargo: {lead_title}

{script_instructions}

{conversation_context}

Estado actual de la conversacion: {state}

Segun el estado de la conversacion:
- greeting: Presentate y explica el motivo de la llamada
- qualification: Haz preguntas de calificacion
- offer: Presenta la propuesta de valor
- objection_handling: Aborda las objeciones con empatia
- closing: Resume el valor y sugiere proximos pasos

Devuelve tu respuesta como un objeto JSON con estos campos:
- response_text: Tu respuesta hablada (natural y breve)
- new_state: El siguiente estado de la conversacion

Solo devuelve el objeto JSON, sin otro texto.
""",
    "de": """\
Sie sind ein KI-Sprachverkaufsassistent, der ausgehende Anrufe im Namen eines Unternehmens tatigt.
Ihr Ziel ist es, ein naturliches, professionelles Telefongesprach zu fuhren, das den Interessenten qualifiziert und zu einem Meeting oder Verkauf fuhrt.

Richtlinien:
- Sprechen Sie naturlich und gesprächig, wie bei einem echten Telefonat
- Halten Sie Antworten kurz (maximal 1-3 Satze)
- Seien Sie empathisch und horen Sie aktiv zu
- Seien Sie niemals aufdringlich oder aggressiv
- Wenn der Interessent nicht interessiert ist, beenden Sie das Gesprach hoflich

{personality_instructions}

Lead-Kontext:
- Name: {lead_name}
- Unternehmen: {lead_company}
- Position: {lead_title}

{script_instructions}

{conversation_context}

Aktueller Gesprachszustand: {state}

Basierend auf dem Gesprachszustand:
- greeting: Stellen Sie sich vor und nennen Sie den Grund des Anrufs
- qualification: Stellen Sie qualifizierende Fragen
- offer: Prasentieren Sie das Wertversprechen
- objection_handling: Gehen Sie auf Einwande ein
- closing: Fassen Sie den Wert zusammen und schlagen Sie nachste Schritte vor

Geben Sie Ihre Antwort als JSON-Objekt mit diesen Feldern zuruck:
- response_text: Ihre gesprochene Antwort (naturlich und kurz)
- new_state: Der nachste Gesprachszustand

Geben Sie nur das JSON-Objekt zuruck, keinen anderen Text.
""",
}

GREETING_PROMPT = """\
You are an AI voice sales assistant. Generate a natural, warm greeting for an outbound call.

{personality_instructions}

Lead context:
- Name: {lead_name}
- Company: {lead_company}
- Title: {lead_title}

{script_instructions}

{conversation_context}

Generate a brief, natural greeting (1-2 sentences) that:
1. Introduces yourself by name (use the company name from the script if available)
2. States why you are calling in a non-intrusive way
3. Asks if now is a good time

Return only the greeting text, no JSON or additional formatting.
"""


def detect_language(lead_data: dict[str, Any]) -> str:
    """Detect the preferred language for a lead based on enrichment data.

    Checks lead enrichment_data for country or locale fields and maps
    to a supported language code. Falls back to 'en' if not found.

    Args:
        lead_data: Lead data dict, may include enrichment_data with country/locale.

    Returns:
        Language code string (en, ru, es, de).
    """
    from channels.voice.stt import LANGUAGE_MAP

    enrichment = lead_data.get("enrichment_data", {})
    if not enrichment:
        enrichment = {}

    # Check locale first (e.g., "ru_RU", "es_MX")
    locale = enrichment.get("locale", "")
    if locale:
        lang_part = locale.split("_")[0].lower()
        supported = {"en", "ru", "es", "de"}
        if lang_part in supported:
            return lang_part

    # Check country code
    country = enrichment.get("country", "").upper()
    if country and country in LANGUAGE_MAP:
        return LANGUAGE_MAP[country]

    return "en"


class VoiceConversationAgent:
    """Manages AI-powered voice conversations with leads."""

    def __init__(
        self,
        llm_client: LLMClient,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._llm = llm_client
        self._settings = settings
        self._session_factory = session_factory
        self._interrupted = False

    async def load_conversation_history(self, lead_id: UUID, session: AsyncSession) -> str:
        """Load previous interaction history for a lead from lead_interactions table.

        Queries past interactions and builds a summary string for prompt context.

        Args:
            lead_id: UUID of the lead.
            session: Active async database session.

        Returns:
            Summary string of past interactions, or empty string if none.
        """
        try:
            from core.models import LeadInteraction
            result = await session.execute(
                select(LeadInteraction)
                .where(LeadInteraction.lead_id == lead_id)
                .order_by(LeadInteraction.created_at.desc())
                .limit(5)
            )
            interactions = result.scalars().all()

            if not interactions:
                return ""

            summaries = []
            for interaction in reversed(interactions):
                channel = interaction.channel or interaction.interaction_type
                summary = interaction.summary or "No summary"
                created = interaction.created_at.strftime("%Y-%m-%d") if interaction.created_at else "unknown date"
                summaries.append(f"- {created} ({channel}): {summary}")

            return "Previous interactions with this lead:\n" + "\n".join(summaries)
        except Exception as exc:
            logger.debug("Could not load conversation history: %s", exc)
            return ""

    async def save_interaction(
        self,
        lead_id: UUID,
        tenant_id: UUID,
        interaction_type: str,
        channel: str,
        summary: str,
        context_json: dict[str, Any] | None = None,
    ) -> None:
        """Save a call interaction to the lead_interactions table.

        Args:
            lead_id: UUID of the lead.
            tenant_id: UUID of the tenant.
            interaction_type: Type of interaction (call, email, linkedin).
            channel: Channel used.
            summary: Summary of the interaction.
            context_json: Optional JSON context data.
        """
        try:
            from core.models import LeadInteraction
            async with self._session_factory() as session:
                interaction = LeadInteraction(
                    lead_id=lead_id,
                    tenant_id=tenant_id,
                    interaction_type=interaction_type,
                    channel=channel,
                    summary=summary,
                    context_json=context_json or {},
                )
                session.add(interaction)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to save interaction: %s", exc)

    async def generate_greeting(
        self, lead_data: dict[str, Any], script: dict[str, Any] | None = None
    ) -> str:
        """Generate an initial greeting for the call.

        Args:
            lead_data: Information about the lead being called.
            script: Optional call script with greeting template and personality settings.

        Returns:
            Greeting text to be spoken via TTS.
        """
        personality_instructions = ""
        script_instructions = ""
        conversation_context = ""

        if script:
            personality = script.get("personality", {})
            if personality:
                tone = personality.get("tone", "professional and friendly")
                pace = personality.get("pace", "moderate")
                personality_instructions = (
                    f"Personality: Speak with a {tone} tone at a {pace} pace."
                )
            greeting_template = script.get("greeting_template")
            if greeting_template:
                script_instructions = f"Use this as a guide for your greeting: {greeting_template}"
            company_name = script.get("company_name", "")
            if company_name:
                script_instructions += f"\nYou are calling on behalf of: {company_name}"

        # Load conversation history if lead_id available
        lead_id = lead_data.get("id")
        if lead_id:
            try:
                async with self._session_factory() as session:
                    conversation_context = await self.load_conversation_history(
                        UUID(str(lead_id)) if isinstance(lead_id, str) else lead_id,
                        session,
                    )
            except Exception as exc:
                logger.debug("Could not load history for greeting: %s", exc)

        prompt = GREETING_PROMPT.format(
            lead_name=f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
            lead_company=lead_data.get("company", "Unknown"),
            lead_title=lead_data.get("title", ""),
            personality_instructions=personality_instructions,
            script_instructions=script_instructions,
            conversation_context=conversation_context,
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._llm.generate(
                messages=messages,
                temperature=0.7,
                max_tokens=256,
            )
            return response.strip()
        except Exception as exc:
            logger.error("Failed to generate greeting: %s", exc)
            first_name = lead_data.get("first_name", "there")
            return f"Hi {first_name}, this is your AI sales assistant calling. Do you have a moment to chat?"

    async def process_transcript(
        self,
        transcript: str,
        state: ConversationState,
        lead_data: dict[str, Any],
        conversation_history: list[dict[str, Any]],
        script: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a transcript segment and generate a response.

        Args:
            transcript: The latest speech-to-text result from the prospect.
            state: Current conversation state.
            lead_data: Information about the lead.
            conversation_history: Previous turns in the conversation.
            script: Optional call script with personality and topic guidance.

        Returns:
            Dict with 'response_text' and 'new_state'.
        """
        self._interrupted = False

        personality_instructions = ""
        script_instructions = ""
        conversation_context = ""

        if script:
            personality = script.get("personality", {})
            if personality:
                tone = personality.get("tone", "professional and friendly")
                pace = personality.get("pace", "moderate")
                personality_instructions = (
                    f"Personality: Speak with a {tone} tone at a {pace} pace."
                )
            topics = script.get("topics", [])
            if topics:
                script_instructions = f"Key topics to cover: {', '.join(topics)}"
            value_prop = script.get("value_proposition", "")
            if value_prop:
                script_instructions += f"\nValue proposition: {value_prop}"

        # Load conversation memory
        lead_id = lead_data.get("id")
        if lead_id:
            try:
                async with self._session_factory() as session:
                    conversation_context = await self.load_conversation_history(
                        UUID(str(lead_id)) if isinstance(lead_id, str) else lead_id,
                        session,
                    )
            except Exception as exc:
                logger.debug("Could not load history for transcript processing: %s", exc)

        # Select language-appropriate system prompt
        language = detect_language(lead_data)
        system_prompt_template = VOICE_SYSTEM_PROMPTS.get(language, VOICE_SYSTEM_PROMPTS["en"])

        system_prompt = system_prompt_template.format(
            lead_name=f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
            lead_company=lead_data.get("company", "Unknown"),
            lead_title=lead_data.get("title", ""),
            state=state.value,
            personality_instructions=personality_instructions,
            script_instructions=script_instructions,
            conversation_context=conversation_context,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # Add conversation history
        for turn in conversation_history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            messages.append({"role": role, "content": content})

        # Add the latest transcript
        messages.append({"role": "user", "content": transcript})

        try:
            response = await self._llm.generate(
                messages=messages,
                temperature=0.7,
                max_tokens=512,
            )

            if self._interrupted:
                return {"response_text": "", "new_state": state}

            result = json.loads(response)
            new_state_str = result.get("new_state", state.value)
            try:
                new_state = ConversationState(new_state_str)
            except ValueError:
                new_state = state

            return {
                "response_text": result.get("response_text", ""),
                "new_state": new_state,
            }
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse voice conversation response: %s", exc)
            return {
                "response_text": "I appreciate your time. Could you tell me more about that?",
                "new_state": state,
            }

    async def handle_interrupt(self) -> None:
        """Signal that the current response generation should be interrupted.

        Sets an internal flag to stop TTS playback when the prospect speaks.
        """
        self._interrupted = True

    async def should_end_call(
        self,
        state: ConversationState,
        duration_seconds: int,
        max_duration: int,
    ) -> bool:
        """Determine if the call should be ended.

        Args:
            state: Current conversation state.
            duration_seconds: How long the call has been going.
            max_duration: Maximum allowed call duration in seconds.

        Returns:
            True if the call should end.
        """
        if state == ConversationState.ended:
            return True
        if duration_seconds >= max_duration:
            return True
        return False
