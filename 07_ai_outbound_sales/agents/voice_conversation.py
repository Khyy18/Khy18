"""Voice Conversation Agent - manages AI-powered voice call conversations."""

from __future__ import annotations

import enum
import json
import logging
from typing import Any

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

GREETING_PROMPT = """\
You are an AI voice sales assistant. Generate a natural, warm greeting for an outbound call.

{personality_instructions}

Lead context:
- Name: {lead_name}
- Company: {lead_company}
- Title: {lead_title}

{script_instructions}

Generate a brief, natural greeting (1-2 sentences) that:
1. Introduces yourself by name (use the company name from the script if available)
2. States why you are calling in a non-intrusive way
3. Asks if now is a good time

Return only the greeting text, no JSON or additional formatting.
"""


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

        prompt = GREETING_PROMPT.format(
            lead_name=f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
            lead_company=lead_data.get("company", "Unknown"),
            lead_title=lead_data.get("title", ""),
            personality_instructions=personality_instructions,
            script_instructions=script_instructions,
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

        system_prompt = VOICE_SYSTEM_PROMPT.format(
            lead_name=f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
            lead_company=lead_data.get("company", "Unknown"),
            lead_title=lead_data.get("title", ""),
            state=state.value,
            personality_instructions=personality_instructions,
            script_instructions=script_instructions,
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
