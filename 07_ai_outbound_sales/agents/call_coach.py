"""AI Call Coaching Agent - analyzes call transcripts and provides coaching feedback."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.llm import LLMClient
from core.models import Call

logger = logging.getLogger(__name__)


@dataclass
class CallCoachingResult:
    """Structured coaching result from call analysis."""

    call_id: UUID
    talk_to_listen_ratio: float = 0.0
    objection_handling_score: int = 0
    closing_technique_score: int = 0
    overall_score: int = 0
    improvement_suggestions: list[str] = field(default_factory=list)
    script_improvement_suggestions: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "call_id": str(self.call_id),
            "talk_to_listen_ratio": self.talk_to_listen_ratio,
            "objection_handling_score": self.objection_handling_score,
            "closing_technique_score": self.closing_technique_score,
            "overall_score": self.overall_score,
            "improvement_suggestions": self.improvement_suggestions,
            "script_improvement_suggestions": self.script_improvement_suggestions,
        }


COACHING_PROMPT = """\
You are an expert sales call coach. Analyze the following call transcript and provide detailed coaching feedback.

Transcript:
{transcript}

Analyze the call and return a JSON object with the following fields:
- talk_to_listen_ratio: float between 0 and 1 representing the percentage of time the agent spoke vs the prospect (0.5 means equal, >0.5 means agent talked more)
- objection_handling_score: integer 0-100 rating how well objections were handled
- closing_technique_score: integer 0-100 rating the closing technique
- overall_score: integer 0-100 overall call quality score
- improvement_suggestions: list of 2-5 specific, actionable improvement suggestions
- script_improvement_suggestions: list of objects with "current_phrase" and "suggested_phrase" fields showing specific script improvements

Only return the JSON object, no other text.
"""


class CallCoachAgent:
    """Analyzes call transcripts and provides AI-powered coaching feedback."""

    def __init__(
        self,
        llm_client: LLMClient,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._llm = llm_client
        self._settings = settings
        self._session_factory = session_factory

    async def analyze_call(self, call_id: UUID) -> CallCoachingResult:
        """Analyze a completed call and return coaching feedback.

        Args:
            call_id: UUID of the call to analyze.

        Returns:
            CallCoachingResult with scores and suggestions.

        Raises:
            ValueError: If call not found or has no transcript.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Call).where(Call.id == call_id)
            )
            call = result.scalar_one_or_none()

            if call is None:
                raise ValueError(f"Call {call_id} not found")

            if not call.transcript:
                raise ValueError(f"Call {call_id} has no transcript")

            transcript = call.transcript

        # Use LLM to analyze the transcript
        prompt = COACHING_PROMPT.format(transcript=transcript)
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._llm.generate(
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )

            data = json.loads(response)

            return CallCoachingResult(
                call_id=call_id,
                talk_to_listen_ratio=float(data.get("talk_to_listen_ratio", 0.5)),
                objection_handling_score=int(data.get("objection_handling_score", 50)),
                closing_technique_score=int(data.get("closing_technique_score", 50)),
                overall_score=int(data.get("overall_score", 50)),
                improvement_suggestions=data.get("improvement_suggestions", []),
                script_improvement_suggestions=data.get("script_improvement_suggestions", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Failed to parse coaching response: %s", exc)
            return CallCoachingResult(
                call_id=call_id,
                talk_to_listen_ratio=0.5,
                objection_handling_score=50,
                closing_technique_score=50,
                overall_score=50,
                improvement_suggestions=["Unable to analyze transcript - please try again"],
                script_improvement_suggestions=[],
            )
