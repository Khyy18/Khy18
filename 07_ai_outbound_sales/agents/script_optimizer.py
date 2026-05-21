"""Script Optimizer Agent - analyzes call data and suggests script improvements."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Call, CallOutcome, CallScript

logger = logging.getLogger(__name__)


class ScriptAnalysis(BaseModel):
    """Analysis results for a call script."""

    total_calls: int = 0
    success_rate: float = 0.0
    top_performing_phrases: list[str] = []
    underperforming_phrases: list[str] = []


class OptimizationSuggestion(BaseModel):
    """A single optimization suggestion for a script section."""

    section: str  # greeting, qualification, offer, closing
    current_approach: str
    suggested_approach: str
    expected_improvement: float  # 0-1
    confidence: float  # 0-1
    supporting_evidence: str


ANALYSIS_PROMPT = """\
You are an expert sales script analyst. Analyze the following call transcripts and their outcomes.

Successful calls (resulted in qualification):
{successful_transcripts}

Unsuccessful calls (resulted in not_interested or other negative outcomes):
{unsuccessful_transcripts}

Identify which phrases, approaches, and patterns correlate with success vs failure.

Return a JSON object with:
- top_performing_phrases: list of 3-5 phrases/approaches that correlate with success
- underperforming_phrases: list of 3-5 phrases/approaches that correlate with failure

Only return the JSON object, no other text.
"""

OPTIMIZATION_PROMPT = """\
You are an expert sales script optimizer. Based on the following script and performance data, suggest improvements.

Current script:
{script_json}

Performance data:
- Total calls: {total_calls}
- Success rate: {success_rate:.1%}
- Top performing phrases: {top_phrases}
- Underperforming phrases: {under_phrases}

Suggest 3-5 specific improvements. For each, specify the script section (greeting, qualification, offer, or closing), the current approach, a better approach, expected improvement (0.0-1.0), confidence (0.0-1.0), and supporting evidence.

Return a JSON array of objects, each with fields: section, current_approach, suggested_approach, expected_improvement, confidence, supporting_evidence.

Only return the JSON array, no other text.
"""


class ScriptOptimizerAgent:
    """Analyzes conversion data across calls and suggests script modifications."""

    def __init__(
        self,
        llm_client: Any,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Any,
    ) -> None:
        self._llm = llm_client
        self._session_factory = session_factory
        self._settings = settings

    async def analyze_script_performance(self, script_id: UUID) -> ScriptAnalysis:
        """Load all calls using this script, compare transcripts with outcomes.

        Uses LLM to identify which phrases/approaches correlate with success.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Call).where(Call.script_id == script_id)
            )
            calls = result.scalars().all()

        if not calls:
            return ScriptAnalysis(total_calls=0, success_rate=0.0)

        total = len(calls)
        successful = [c for c in calls if c.outcome == CallOutcome.qualified]
        unsuccessful = [
            c for c in calls if c.outcome == CallOutcome.not_interested
        ]
        success_rate = len(successful) / total if total > 0 else 0.0

        # If we have transcripts, use LLM to analyze
        successful_transcripts = [
            c.transcript for c in successful if c.transcript
        ][:5]
        unsuccessful_transcripts = [
            c.transcript for c in unsuccessful if c.transcript
        ][:5]

        if not successful_transcripts and not unsuccessful_transcripts:
            return ScriptAnalysis(
                total_calls=total,
                success_rate=success_rate,
            )

        prompt = ANALYSIS_PROMPT.format(
            successful_transcripts="\n---\n".join(successful_transcripts) or "None available",
            unsuccessful_transcripts="\n---\n".join(unsuccessful_transcripts) or "None available",
        )

        try:
            response = await self._llm.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            data = json.loads(response)
            return ScriptAnalysis(
                total_calls=total,
                success_rate=success_rate,
                top_performing_phrases=data.get("top_performing_phrases", []),
                underperforming_phrases=data.get("underperforming_phrases", []),
            )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to parse script analysis: %s", exc)
            return ScriptAnalysis(total_calls=total, success_rate=success_rate)

    async def get_optimization_suggestions(
        self, script_id: UUID
    ) -> list[OptimizationSuggestion]:
        """Generate optimization suggestions for a script based on performance data."""
        analysis = await self.analyze_script_performance(script_id)

        async with self._session_factory() as session:
            result = await session.execute(
                select(CallScript).where(CallScript.id == script_id)
            )
            script = result.scalar_one_or_none()

        if script is None:
            return []

        prompt = OPTIMIZATION_PROMPT.format(
            script_json=json.dumps(script.script_json),
            total_calls=analysis.total_calls,
            success_rate=analysis.success_rate,
            top_phrases=", ".join(analysis.top_performing_phrases) or "N/A",
            under_phrases=", ".join(analysis.underperforming_phrases) or "N/A",
        )

        try:
            response = await self._llm.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2048,
            )
            data = json.loads(response)
            suggestions = []
            for item in data:
                suggestions.append(
                    OptimizationSuggestion(
                        section=item.get("section", "greeting"),
                        current_approach=item.get("current_approach", ""),
                        suggested_approach=item.get("suggested_approach", ""),
                        expected_improvement=float(item.get("expected_improvement", 0.1)),
                        confidence=float(item.get("confidence", 0.5)),
                        supporting_evidence=item.get("supporting_evidence", ""),
                    )
                )
            return suggestions
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to parse optimization suggestions: %s", exc)
            return []

    async def create_ab_test_variant(
        self, script_id: UUID, suggestion_index: int
    ) -> UUID:
        """Create a variant CallScript for A/B testing based on a suggestion."""
        suggestions = await self.get_optimization_suggestions(script_id)

        async with self._session_factory() as session:
            result = await session.execute(
                select(CallScript).where(CallScript.id == script_id)
            )
            script = result.scalar_one_or_none()

            if script is None:
                raise ValueError(f"Script {script_id} not found")

            # Apply the suggestion to create a variant
            variant_json = dict(script.script_json) if script.script_json else {}
            if 0 <= suggestion_index < len(suggestions):
                suggestion = suggestions[suggestion_index]
                variant_json["_variant_note"] = (
                    f"A/B variant: {suggestion.section} - {suggestion.suggested_approach}"
                )
                variant_json[f"optimized_{suggestion.section}"] = suggestion.suggested_approach

            variant_id = uuid.uuid4()
            variant = CallScript(
                id=variant_id,
                tenant_id=script.tenant_id,
                name=f"{script.name} (A/B Variant)",
                script_json=variant_json,
                voice_id=script.voice_id,
                language=script.language,
            )
            session.add(variant)
            await session.commit()

        return variant_id
