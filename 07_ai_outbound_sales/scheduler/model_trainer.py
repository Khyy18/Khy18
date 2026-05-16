"""Model Trainer Job - retrains ML lead scoring model on schedule."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.ml_scorer import MLLeadScorer, InsufficientDataError
from core.models import Event, EventType, Lead, LeadStatus, Message

logger = logging.getLogger(__name__)


class ModelTrainerJob:
    """Retrains the ML lead scoring model periodically (designed for weekly cron)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        model_dir: str = "models/",
        redis_url: str = "redis://localhost:6379/0",
    ) -> None:
        self._session_factory = session_factory
        self._model_dir = model_dir
        self._redis_url = redis_url

    async def retrain(self) -> dict[str, Any]:
        """Query leads with engagement data, engineer features, train model, and save.

        Returns:
            Dict with training metrics and model version info.

        Raises:
            InsufficientDataError: If not enough training data available.
        """
        logger.info("Starting model retraining job")

        # Gather training data from database
        training_data = await self._gather_training_data()
        logger.info("Gathered %d training samples", len(training_data))

        # Train the model
        scorer = MLLeadScorer()
        metrics = scorer.train(training_data)

        # Save model with version suffix
        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_filename = f"lead_scorer_v{version}.joblib"
        model_path = os.path.join(self._model_dir, model_filename)
        latest_path = os.path.join(self._model_dir, "lead_scorer_latest.joblib")

        scorer.save_model(model_path)
        scorer.save_model(latest_path)

        # Update Redis with current model version info
        redis = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            await redis.hset("ml_model:current_version", mapping={
                "version": version,
                "filename": model_filename,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "auc": str(metrics["auc"]),
                "precision": str(metrics["precision"]),
                "recall": str(metrics["recall"]),
                "n_samples": str(metrics["n_samples"]),
            })
        finally:
            await redis.close()

        logger.info("Model retrained successfully: version=%s, metrics=%s", version, metrics)

        return {
            "version": version,
            "model_path": model_path,
            "metrics": metrics,
        }

    async def get_current_model_info(self) -> dict[str, Any]:
        """Return current model version, training date, and metrics from Redis.

        Returns:
            Dict with model version info, or empty dict if no model exists.
        """
        redis = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            info = await redis.hgetall("ml_model:current_version")
            if not info:
                return {}
            return {
                "version": info.get("version", ""),
                "filename": info.get("filename", ""),
                "trained_at": info.get("trained_at", ""),
                "metrics": {
                    "auc": float(info.get("auc", 0)),
                    "precision": float(info.get("precision", 0)),
                    "recall": float(info.get("recall", 0)),
                    "n_samples": int(info.get("n_samples", 0)),
                },
            }
        finally:
            await redis.close()

    async def _gather_training_data(self) -> list[dict[str, Any]]:
        """Query leads and their engagement data to build training set.

        Positive label: lead.status == booked
        Negative label: lead.status in (lost, contacted) with sufficient history.

        Returns:
            List of dicts with 'features' and 'label' keys.
        """
        training_data: list[dict[str, Any]] = []
        scorer = MLLeadScorer()

        async with self._session_factory() as session:
            # Get leads with definitive outcomes
            result = await session.execute(
                select(Lead).where(
                    Lead.status.in_([
                        LeadStatus.booked,
                        LeadStatus.lost,
                        LeadStatus.contacted,
                        LeadStatus.qualified,
                    ])
                )
            )
            leads = list(result.scalars().all())

            for lead in leads:
                # Get engagement data for this lead
                msg_result = await session.execute(
                    select(Message.id).where(Message.lead_id == lead.id)
                )
                message_ids = [row[0] for row in msg_result.all()]

                engagement_data = await self._build_engagement_data(
                    session, lead, message_ids
                )

                # Build lead data for feature engineering
                enrichment = lead.enrichment_data or {}
                lead_data = {
                    "company_size": enrichment.get("company_size", 50),
                    "industry": enrichment.get("industry", "unknown"),
                    "title": lead.title or "",
                    "trigger_events": enrichment.get("trigger_events", []),
                    "tech_stack_overlap_score": enrichment.get("tech_stack_overlap_score", 0.0),
                }

                features = scorer.engineer_features(lead_data, engagement_data)
                label = 1 if lead.status == LeadStatus.booked else 0

                training_data.append({
                    "features": features,
                    "label": label,
                })

        return training_data

    async def _build_engagement_data(
        self,
        session: AsyncSession,
        lead: Lead,
        message_ids: list,
    ) -> dict[str, Any]:
        """Build engagement data dict for a lead from its messages and events."""
        from sqlalchemy import func

        engagement: dict[str, Any] = {
            "email_open_count": 0,
            "email_click_count": 0,
            "time_to_first_open_hours": -1,
            "linkedin_engagement_score": 0.0,
            "sequence_step_reached": 0,
            "day_of_week_sent": 0,
            "hour_sent": 9,
        }

        if not message_ids:
            return engagement

        # Count opens and clicks
        open_result = await session.execute(
            select(func.count()).select_from(Event).where(
                Event.message_id.in_(message_ids),
                Event.event_type == EventType.open,
            )
        )
        engagement["email_open_count"] = open_result.scalar() or 0

        click_result = await session.execute(
            select(func.count()).select_from(Event).where(
                Event.message_id.in_(message_ids),
                Event.event_type == EventType.click,
            )
        )
        engagement["email_click_count"] = click_result.scalar() or 0

        engagement["sequence_step_reached"] = len(message_ids)

        return engagement
