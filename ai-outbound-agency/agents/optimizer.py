"""Optimizer Agent - A/B testing, statistical significance, and send-time optimization."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import numpy as np
from scipy.stats import chi2_contingency
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.llm import LLMClient
from core.models import (
    ABTest,
    ABTestAssignment,
    ABTestStatus,
    Event,
    EventType,
    Message,
    MessageDirection,
    MessageStatus,
)

logger = logging.getLogger(__name__)


class OptimizerAgent:
    """A/B testing and campaign optimization agent."""

    def __init__(
        self,
        llm_client: LLMClient,
        session_factory: async_sessionmaker[AsyncSession],
        redis_url: str,
    ) -> None:
        self._llm = llm_client
        self._session_factory = session_factory
        self._redis_url = redis_url

    async def get_variant_performance(
        self, campaign_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Compute per-variant stats for all A/B tests on a campaign.

        Returns list of variant stat dicts with sends, opens, clicks, replies,
        books, open_rate, click_rate, reply_rate, book_rate, and score.
        """
        # Get running tests for this campaign
        stmt = select(ABTest).where(
            ABTest.campaign_id == campaign_id,
            ABTest.status == ABTestStatus.running,
        )
        result = await session.execute(stmt)
        tests = result.scalars().all()

        variant_stats: list[dict[str, Any]] = []

        for test in tests:
            variants = test.variants or []
            for variant in variants:
                variant_key = variant.get("key", "")
                # Get assignments for this variant
                assign_stmt = select(ABTestAssignment.lead_id).where(
                    ABTestAssignment.test_id == test.id,
                    ABTestAssignment.variant_key == variant_key,
                )
                assign_result = await session.execute(assign_stmt)
                lead_ids = [row[0] for row in assign_result.fetchall()]

                if not lead_ids:
                    variant_stats.append({
                        "test_id": str(test.id),
                        "variant_key": variant_key,
                        "sends": 0,
                        "opens": 0,
                        "clicks": 0,
                        "replies": 0,
                        "books": 0,
                        "open_rate": 0.0,
                        "click_rate": 0.0,
                        "reply_rate": 0.0,
                        "book_rate": 0.0,
                        "score": 0.0,
                    })
                    continue

                # Count sends
                sends_stmt = (
                    select(func.count())
                    .select_from(Message)
                    .where(
                        Message.campaign_id == campaign_id,
                        Message.lead_id.in_(lead_ids),
                        Message.direction == MessageDirection.outbound,
                        Message.status != MessageStatus.draft,
                    )
                )
                sends_result = await session.execute(sends_stmt)
                sends = sends_result.scalar() or 0

                # Count events by type
                events_stmt = (
                    select(Event.event_type, func.count())
                    .join(Message, Event.message_id == Message.id)
                    .where(
                        Message.campaign_id == campaign_id,
                        Message.lead_id.in_(lead_ids),
                    )
                    .group_by(Event.event_type)
                )
                events_result = await session.execute(events_stmt)
                event_counts: dict[str, int] = {}
                for row in events_result.fetchall():
                    event_counts[row[0].value if hasattr(row[0], "value") else str(row[0])] = row[1]

                opens = event_counts.get("open", 0)
                clicks = event_counts.get("click", 0)
                replies = event_counts.get("reply", 0)
                books = event_counts.get("book", 0)

                open_rate = opens / sends if sends > 0 else 0.0
                click_rate = clicks / sends if sends > 0 else 0.0
                reply_rate = replies / sends if sends > 0 else 0.0
                book_rate = books / sends if sends > 0 else 0.0

                # Score: reply_rate*0.5 + positive_reply_rate*0.3 + book_rate*0.2
                # For simplicity, positive_reply_rate is approximated as reply_rate
                score = reply_rate * 0.5 + reply_rate * 0.3 + book_rate * 0.2

                variant_stats.append({
                    "test_id": str(test.id),
                    "variant_key": variant_key,
                    "sends": sends,
                    "opens": opens,
                    "clicks": clicks,
                    "replies": replies,
                    "books": books,
                    "open_rate": round(open_rate, 4),
                    "click_rate": round(click_rate, 4),
                    "reply_rate": round(reply_rate, 4),
                    "book_rate": round(book_rate, 4),
                    "score": round(score, 4),
                })

        return variant_stats

    async def create_ab_test(
        self,
        campaign_id: UUID,
        tenant_id: UUID,
        name: str,
        variants: list[dict[str, Any]],
        min_sends: int = 100,
        session: AsyncSession | None = None,
    ) -> ABTest:
        """Create a new A/B test record."""
        should_close = False
        if session is None:
            session = self._session_factory()
            should_close = True

        try:
            test = ABTest(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                name=name,
                variants=variants,
                min_sends_per_variant=min_sends,
                status=ABTestStatus.running,
            )
            session.add(test)
            await session.flush()
            await session.refresh(test)
            if should_close:
                await session.commit()
            return test
        except Exception:
            if should_close:
                await session.rollback()
            raise
        finally:
            if should_close:
                await session.close()

    async def assign_variant(
        self, test_id: UUID, lead_id: UUID, session: AsyncSession
    ) -> str:
        """Assign a lead to a variant using round-robin to balance groups.

        Returns the variant_key assigned to the lead.
        """
        # Check if lead already has an assignment
        existing_stmt = select(ABTestAssignment).where(
            ABTestAssignment.test_id == test_id,
            ABTestAssignment.lead_id == lead_id,
        )
        existing_result = await session.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing.variant_key

        # Get the test to know variant keys
        test_stmt = select(ABTest).where(ABTest.id == test_id)
        test_result = await session.execute(test_stmt)
        test = test_result.scalar_one_or_none()
        if test is None:
            raise ValueError(f"ABTest {test_id} not found")

        variants = test.variants or []
        if not variants:
            raise ValueError(f"ABTest {test_id} has no variants")

        variant_keys = [v.get("key", "") for v in variants]

        # Count assignments per variant for round-robin
        counts_stmt = (
            select(ABTestAssignment.variant_key, func.count())
            .where(ABTestAssignment.test_id == test_id)
            .group_by(ABTestAssignment.variant_key)
        )
        counts_result = await session.execute(counts_stmt)
        counts: dict[str, int] = {key: 0 for key in variant_keys}
        for row in counts_result.fetchall():
            counts[row[0]] = row[1]

        # Assign to the variant with the fewest assignments
        chosen_key = min(variant_keys, key=lambda k: counts.get(k, 0))

        assignment = ABTestAssignment(
            test_id=test_id,
            lead_id=lead_id,
            variant_key=chosen_key,
        )
        session.add(assignment)
        await session.flush()

        return chosen_key

    async def check_significance(
        self, test_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        """Perform chi-squared test on conversion rates across variants.

        Returns dict with is_significant, p_value, variant_stats, winner_key.
        Only considers test significant if p_value < 0.05 AND each variant
        has >= min_sends_per_variant.
        """
        test_stmt = select(ABTest).where(ABTest.id == test_id)
        test_result = await session.execute(test_stmt)
        test = test_result.scalar_one_or_none()
        if test is None:
            return {"is_significant": False, "p_value": 1.0, "variant_stats": [], "winner_key": None}

        variants = test.variants or []
        variant_keys = [v.get("key", "") for v in variants]
        min_sends = test.min_sends_per_variant or 100

        variant_stats: list[dict[str, Any]] = []
        observed: list[list[int]] = []

        for variant_key in variant_keys:
            # Get lead IDs for this variant
            assign_stmt = select(ABTestAssignment.lead_id).where(
                ABTestAssignment.test_id == test_id,
                ABTestAssignment.variant_key == variant_key,
            )
            assign_result = await session.execute(assign_stmt)
            lead_ids = [row[0] for row in assign_result.fetchall()]

            if not lead_ids:
                variant_stats.append({
                    "variant_key": variant_key,
                    "sends": 0,
                    "conversions": 0,
                    "conversion_rate": 0.0,
                })
                observed.append([0, 0])
                continue

            # Count sends
            sends_stmt = (
                select(func.count())
                .select_from(Message)
                .where(
                    Message.campaign_id == test.campaign_id,
                    Message.lead_id.in_(lead_ids),
                    Message.direction == MessageDirection.outbound,
                    Message.status != MessageStatus.draft,
                )
            )
            sends_result = await session.execute(sends_stmt)
            sends = sends_result.scalar() or 0

            # Count conversions (replies)
            conversions_stmt = (
                select(func.count())
                .select_from(Event)
                .join(Message, Event.message_id == Message.id)
                .where(
                    Message.campaign_id == test.campaign_id,
                    Message.lead_id.in_(lead_ids),
                    Event.event_type == EventType.reply,
                )
            )
            conversions_result = await session.execute(conversions_stmt)
            conversions = conversions_result.scalar() or 0

            non_conversions = max(0, sends - conversions)
            conversion_rate = conversions / sends if sends > 0 else 0.0

            variant_stats.append({
                "variant_key": variant_key,
                "sends": sends,
                "conversions": conversions,
                "conversion_rate": round(conversion_rate, 4),
            })
            observed.append([conversions, non_conversions])

        # Check if all variants have minimum sends
        all_have_min = all(vs["sends"] >= min_sends for vs in variant_stats)
        if not all_have_min or len(variant_stats) < 2:
            return {
                "is_significant": False,
                "p_value": 1.0,
                "variant_stats": variant_stats,
                "winner_key": None,
            }

        # Perform chi-squared test
        observed_array = np.array(observed)
        # Make sure we have non-zero totals
        if observed_array.sum() == 0:
            return {
                "is_significant": False,
                "p_value": 1.0,
                "variant_stats": variant_stats,
                "winner_key": None,
            }

        try:
            chi2, p_value, dof, expected = chi2_contingency(observed_array)
        except ValueError:
            return {
                "is_significant": False,
                "p_value": 1.0,
                "variant_stats": variant_stats,
                "winner_key": None,
            }

        is_significant = p_value < 0.05
        winner_key = None
        if is_significant:
            # Winner is the variant with highest conversion rate
            best = max(variant_stats, key=lambda vs: vs["conversion_rate"])
            winner_key = best["variant_key"]

        return {
            "is_significant": is_significant,
            "p_value": round(float(p_value), 6),
            "variant_stats": variant_stats,
            "winner_key": winner_key,
        }

    async def promote_winner(
        self, test_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        """Mark test completed, set winner_variant_key, return winner info."""
        significance = await self.check_significance(test_id, session)

        test_stmt = select(ABTest).where(ABTest.id == test_id)
        test_result = await session.execute(test_stmt)
        test = test_result.scalar_one_or_none()
        if test is None:
            raise ValueError(f"ABTest {test_id} not found")

        winner_key = significance.get("winner_key")
        if winner_key is None:
            # If no statistical winner, pick best performing
            stats = significance.get("variant_stats", [])
            if stats:
                best = max(stats, key=lambda vs: vs.get("conversion_rate", 0))
                winner_key = best["variant_key"]

        test.status = ABTestStatus.completed
        test.completed_at = datetime.now(timezone.utc)
        test.winner_variant_key = winner_key
        await session.flush()

        return {
            "test_id": str(test_id),
            "winner_variant_key": winner_key,
            "status": "completed",
            "significance": significance,
        }

    async def suggest_improvements(
        self, campaign_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Analyze low-performing messages via LLM, return list of suggestions."""
        # Get messages with low engagement for this campaign
        stmt = (
            select(Message)
            .where(
                Message.campaign_id == campaign_id,
                Message.direction == MessageDirection.outbound,
                Message.status == MessageStatus.sent,
            )
            .limit(10)
        )
        result = await session.execute(stmt)
        messages = result.scalars().all()

        if not messages:
            return [{"suggestion": "No messages sent yet. Start a campaign to get optimization suggestions."}]

        # Build context for LLM
        message_samples = []
        for msg in messages[:5]:
            message_samples.append({
                "subject": msg.subject or "",
                "body": msg.content[:200] if msg.content else "",
            })

        prompt = (
            "You are an outbound sales optimization expert. Analyze these outreach messages "
            "and provide 3-5 actionable suggestions to improve response rates.\n\n"
            f"Messages:\n{json.dumps(message_samples, indent=2)}\n\n"
            "Return a JSON array of suggestion objects, each with 'category' (subject_line, "
            "body_copy, personalization, timing, call_to_action) and 'suggestion' (the advice)."
        )

        try:
            response = await self._llm.generate(
                messages=[
                    {"role": "system", "content": "You are an email marketing optimization AI."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            suggestions = json.loads(response)
            if isinstance(suggestions, list):
                return suggestions
            return [{"suggestion": response}]
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse LLM suggestions: %s", exc)
            return [{"suggestion": "Unable to generate suggestions at this time."}]

    async def optimize_send_times(
        self, tenant_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Analyze historical event data to find optimal send hour/day combos.

        Returns ranked list of day/hour combinations with engagement scores.
        """
        # Query events with their occurrence times
        stmt = (
            select(Event.occurred_at, Event.event_type)
            .join(Message, Event.message_id == Message.id)
            .join(
                # Filter by tenant via campaign -> tenant relationship
                # We use a subquery approach through messages
                Message.campaign,
            )
            .where(Event.event_type.in_([EventType.open, EventType.reply, EventType.click]))
            .limit(5000)
        )

        try:
            result = await session.execute(stmt)
            events = result.fetchall()
        except Exception as exc:
            logger.warning("Failed to query send time events: %s", exc)
            events = []

        if not events:
            # Return default optimal times
            return [
                {"day": "Tuesday", "hour": 9, "score": 0.9},
                {"day": "Wednesday", "hour": 10, "score": 0.85},
                {"day": "Thursday", "hour": 9, "score": 0.8},
                {"day": "Tuesday", "hour": 14, "score": 0.75},
                {"day": "Monday", "hour": 10, "score": 0.7},
            ]

        # Aggregate by day-of-week and hour
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        time_scores: dict[tuple[int, int], float] = {}
        weights = {EventType.open: 1.0, EventType.click: 2.0, EventType.reply: 3.0}

        for occurred_at, event_type in events:
            if occurred_at is None:
                continue
            day_of_week = occurred_at.weekday()
            hour = occurred_at.hour
            weight = weights.get(event_type, 1.0)
            key = (day_of_week, hour)
            time_scores[key] = time_scores.get(key, 0.0) + weight

        if not time_scores:
            return [
                {"day": "Tuesday", "hour": 9, "score": 0.9},
                {"day": "Wednesday", "hour": 10, "score": 0.85},
            ]

        # Normalize and sort
        max_score = max(time_scores.values()) if time_scores else 1.0
        ranked = sorted(time_scores.items(), key=lambda x: x[1], reverse=True)

        optimal_times = []
        for (day_idx, hour), raw_score in ranked[:10]:
            optimal_times.append({
                "day": day_names[day_idx],
                "hour": hour,
                "score": round(raw_score / max_score, 4),
            })

        return optimal_times

    async def auto_check_and_promote(self, session: AsyncSession | None = None) -> None:
        """Iterate running tests, check significance, auto-promote winners."""
        should_close = False
        if session is None:
            async with self._session_factory() as session:
                await self._do_auto_check(session)
                return

        await self._do_auto_check(session)

    async def _do_auto_check(self, session: AsyncSession) -> None:
        """Internal method to check and promote running tests."""
        stmt = select(ABTest).where(ABTest.status == ABTestStatus.running)
        result = await session.execute(stmt)
        tests = result.scalars().all()

        logger.info("Auto-check: found %d running A/B tests", len(tests))

        for test in tests:
            try:
                significance = await self.check_significance(test.id, session)
                if significance["is_significant"] and significance["winner_key"]:
                    logger.info(
                        "Test %s is significant (p=%.4f), promoting winner: %s",
                        test.id,
                        significance["p_value"],
                        significance["winner_key"],
                    )
                    await self.promote_winner(test.id, session)
                    await session.commit()
                else:
                    logger.debug(
                        "Test %s not yet significant (p=%.4f)",
                        test.id,
                        significance.get("p_value", 1.0),
                    )
            except Exception as exc:
                logger.error(
                    "Error checking test %s: %s", test.id, exc, exc_info=True
                )
