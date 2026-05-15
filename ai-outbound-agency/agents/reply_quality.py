"""Reply Quality Scorer - evaluates AI-generated responses using LLM-based scoring."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from core.llm import LLMClient

logger = logging.getLogger(__name__)

QUALITY_THRESHOLD = 70
IMPROVEMENT_THRESHOLD = 85

SCORING_SYSTEM_PROMPT = """\
You are an expert evaluator of B2B sales email responses. You evaluate responses on 6 criteria, each scored 1-10:

1. relevance: How relevant is the response to the prospect's message and context?
2. tone: Is the tone professional, friendly, and appropriate for B2B outreach?
3. value_proposition_clarity: Is the value proposition clearly communicated?
4. cta_effectiveness: Is the call-to-action clear, appropriate, and compelling?
5. length_appropriateness: Is the response an appropriate length (not too short, not too long)?
6. no_hallucinations: Does the response avoid making up facts, stats, or claims not supported by the context?

Return your evaluation as a JSON object with these exact fields:
- relevance: int (1-10)
- tone: int (1-10)
- value_proposition_clarity: int (1-10)
- cta_effectiveness: int (1-10)
- length_appropriateness: int (1-10)
- no_hallucinations: int (1-10)
- improvement_suggestions: list of strings with specific suggestions

Only return the JSON object, no other text.
"""


@dataclass
class QualityScore:
    """Structured quality score for an AI-generated response."""

    relevance: int
    tone: int
    value_proposition_clarity: int
    cta_effectiveness: int
    length_appropriateness: int
    no_hallucinations: int
    overall_score: int
    improvement_suggestions: list[str] = field(default_factory=list)
    passed: bool = True

    def __post_init__(self) -> None:
        """Calculate overall_score and passed status."""
        criteria_sum = (
            self.relevance
            + self.tone
            + self.value_proposition_clarity
            + self.cta_effectiveness
            + self.length_appropriateness
            + self.no_hallucinations
        )
        # Weighted average: all criteria equal weight, normalized to 0-100
        self.overall_score = int((criteria_sum / 6) * 10)
        self.passed = self.overall_score >= QUALITY_THRESHOLD


class ReplyQualityScorer:
    """Evaluates AI-generated responses for quality using LLM-based scoring."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def score_response(
        self,
        response_text: str,
        prospect_message: str,
        campaign_context: dict[str, Any],
    ) -> QualityScore:
        """Score an AI-generated response for quality.

        Args:
            response_text: The generated response text to evaluate.
            prospect_message: The original message from the prospect.
            campaign_context: Context about the campaign (company, value prop, etc).

        Returns:
            QualityScore dataclass with all criteria scores and overall score.
        """
        user_prompt = (
            f"Campaign context:\n"
            f"- Company: {campaign_context.get('company_name', 'N/A')}\n"
            f"- Value Proposition: {campaign_context.get('value_proposition', 'N/A')}\n"
            f"- Sender: {campaign_context.get('sender_name', 'N/A')}\n\n"
            f"Prospect's message:\n{prospect_message}\n\n"
            f"AI-generated response to evaluate:\n{response_text}"
        )

        messages = [
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._llm.generate(
                messages=messages,
                temperature=0.1,
                max_tokens=256,
            )
            result = json.loads(response)

            return QualityScore(
                relevance=int(result.get("relevance", 5)),
                tone=int(result.get("tone", 5)),
                value_proposition_clarity=int(result.get("value_proposition_clarity", 5)),
                cta_effectiveness=int(result.get("cta_effectiveness", 5)),
                length_appropriateness=int(result.get("length_appropriateness", 5)),
                no_hallucinations=int(result.get("no_hallucinations", 5)),
                overall_score=0,  # will be calculated in __post_init__
                improvement_suggestions=result.get("improvement_suggestions", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.error("Failed to parse quality score response: %s", exc)
            # Return a conservative middle score on failure
            return QualityScore(
                relevance=5,
                tone=5,
                value_proposition_clarity=5,
                cta_effectiveness=5,
                length_appropriateness=5,
                no_hallucinations=5,
                overall_score=0,
                improvement_suggestions=["Quality scoring failed - manual review recommended"],
            )
