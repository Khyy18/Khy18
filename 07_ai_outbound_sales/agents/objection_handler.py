"""Objection Handler Agent - extracts, stores, and retrieves objection responses."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Call, CallOutcome

logger = logging.getLogger(__name__)


class ExtractedObjection(BaseModel):
    """An objection extracted from a call transcript."""

    objection_text: str
    category: str  # pricing, timing, authority, need, competitor, technical
    context: str


class ObjectionResponse(BaseModel):
    """A stored response to an objection with success metrics."""

    text: str
    success_rate: float = 0.0
    times_used: int = 0


EXTRACT_OBJECTIONS_PROMPT = """\
You are an expert sales analyst. Analyze the following call transcript and identify all objections raised by the prospect.

Transcript:
{transcript}

For each objection, classify it into one of these categories:
- pricing: cost or budget concerns
- timing: not the right time, too busy
- authority: need to check with someone else, not the decision maker
- need: don't see the need, already have a solution
- competitor: using a competitor, comparing options
- technical: technical concerns, integration worries

Return a JSON array of objects, each with fields:
- objection_text: the exact or paraphrased objection
- category: one of the categories above
- context: brief context of when/how it was raised

Only return the JSON array, no other text.
"""


class ObjectionHandler:
    """Extracts objections from transcripts and manages the objection library."""

    def __init__(
        self,
        llm_client: Any,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Any,
    ) -> None:
        self._llm = llm_client
        self._session_factory = session_factory
        self._settings = settings

    async def extract_objections(self, transcript: str) -> list[ExtractedObjection]:
        """Use LLM to identify objections in a call transcript."""
        if not transcript:
            return []

        prompt = EXTRACT_OBJECTIONS_PROMPT.format(transcript=transcript)

        try:
            response = await self._llm.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1024,
            )
            data = json.loads(response)
            objections = []
            for item in data:
                objections.append(
                    ExtractedObjection(
                        objection_text=item.get("objection_text", ""),
                        category=item.get("category", "need"),
                        context=item.get("context", ""),
                    )
                )
            return objections
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to parse objections: %s", exc)
            return []

    async def get_best_response(
        self, objection_text: str, tenant_id: UUID
    ) -> ObjectionResponse | None:
        """Search library for similar objections, return highest-rated response."""
        from core.models import Objection

        async with self._session_factory() as session:
            result = await session.execute(
                select(Objection).where(Objection.tenant_id == tenant_id)
            )
            objections = result.scalars().all()

        if not objections:
            return None

        # Simple keyword matching to find relevant objection
        query_words = set(objection_text.lower().split())
        best_match = None
        best_score = 0

        for obj in objections:
            obj_words = set(obj.objection_text.lower().split())
            overlap = len(query_words & obj_words)
            if overlap > best_score and obj.responses:
                best_score = overlap
                best_match = obj

        if best_match is None or not best_match.responses:
            return None

        # Return the response with highest success rate
        responses = best_match.responses
        best_response = max(responses, key=lambda r: r.get("success_rate", 0))
        return ObjectionResponse(
            text=best_response.get("text", ""),
            success_rate=best_response.get("success_rate", 0.0),
            times_used=best_response.get("times_used", 0),
        )

    async def record_objection_outcome(
        self, objection_id: UUID, response_used: str, outcome: str
    ) -> None:
        """Update success rates in the library based on outcome."""
        from sqlalchemy.orm.attributes import flag_modified

        from core.models import Objection

        async with self._session_factory() as session:
            result = await session.execute(
                select(Objection).where(Objection.id == objection_id)
            )
            objection = result.scalar_one_or_none()

            if objection is None:
                return

            responses = list(objection.responses) if objection.responses else []
            success = 1 if outcome == "success" else 0

            # Find and update the matching response
            found = False
            for resp in responses:
                if resp.get("text") == response_used:
                    times = resp.get("times_used", 0) + 1
                    old_rate = resp.get("success_rate", 0.0)
                    # Running average
                    resp["success_rate"] = (old_rate * (times - 1) + success) / times
                    resp["times_used"] = times
                    found = True
                    break

            if not found:
                responses.append({
                    "text": response_used,
                    "success_rate": float(success),
                    "times_used": 1,
                })

            objection.responses = responses
            flag_modified(objection, "responses")
            await session.commit()

    async def build_library_from_calls(self, tenant_id: UUID) -> None:
        """Batch process all completed calls, extract objections, store in DB."""
        from core.models import Objection
        import uuid

        async with self._session_factory() as session:
            result = await session.execute(
                select(Call).where(
                    Call.tenant_id == tenant_id,
                    Call.transcript.isnot(None),
                    Call.outcome.isnot(None),
                )
            )
            calls = result.scalars().all()

        for call in calls:
            if not call.transcript:
                continue
            extracted = await self.extract_objections(call.transcript)
            if not extracted:
                continue

            async with self._session_factory() as session:
                for obj in extracted:
                    # Check if similar objection already exists
                    existing_result = await session.execute(
                        select(Objection).where(
                            Objection.tenant_id == tenant_id,
                            Objection.category == obj.category,
                            Objection.objection_text == obj.objection_text,
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if existing:
                        existing.times_encountered = (existing.times_encountered or 1) + 1
                    else:
                        new_obj = Objection(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            objection_text=obj.objection_text,
                            category=obj.category,
                            responses=[],
                            times_encountered=1,
                            context=obj.context,
                        )
                        session.add(new_obj)

                await session.commit()
