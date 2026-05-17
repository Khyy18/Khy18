"""Lead Timing Predictor - ML model predicting best contact times."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import numpy as np
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Call, CallOutcome, Lead

logger = logging.getLogger(__name__)


class TimeSlot(BaseModel):
    """A predicted time slot with probability of contact success."""

    day_of_week: int  # 0-6 (Monday-Sunday)
    hour: int  # 0-23
    probability: float
    timezone: str = "UTC"


class TimingPredictor:
    """ML model using gradient boosting to predict best contact times."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Any,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._model = None
        self._encoders: dict[str, dict[str, int]] = {}
        self._is_trained = False

    def _encode_feature(self, category: str, value: str) -> int:
        """Encode a categorical feature using label encoding."""
        if category not in self._encoders:
            self._encoders[category] = {}
        encoder = self._encoders[category]
        if value not in encoder:
            encoder[value] = len(encoder)
        return encoder[value]

    def _extract_features_from_call(self, call: Call, lead: Lead | None) -> list[float]:
        """Extract feature vector from a call and its lead."""
        # Timezone
        tz = "UTC"
        if lead and lead.enrichment_data:
            tz = lead.enrichment_data.get("timezone", "UTC")
        tz_encoded = self._encode_feature("timezone", tz)

        # Industry
        industry = "unknown"
        if lead and lead.enrichment_data:
            industry = lead.enrichment_data.get("industry", "unknown")
        industry_encoded = self._encode_feature("industry", industry)

        # Role/title seniority
        title = "unknown"
        if lead and lead.title:
            title = lead.title.lower()
        seniority = self._classify_seniority(title)
        seniority_encoded = self._encode_feature("seniority", seniority)

        # Day of week and hour from call start time
        day_of_week = call.started_at.weekday() if call.started_at else 0
        hour = call.started_at.hour if call.started_at else 9

        return [tz_encoded, industry_encoded, seniority_encoded, day_of_week, hour]

    def _classify_seniority(self, title: str) -> str:
        """Classify title into seniority level."""
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["ceo", "cto", "cfo", "cmo", "founder", "president"]):
            return "c_level"
        if any(kw in title_lower for kw in ["vp", "vice president", "svp"]):
            return "vp"
        if "director" in title_lower:
            return "director"
        if "manager" in title_lower:
            return "manager"
        if any(kw in title_lower for kw in ["engineer", "developer", "architect"]):
            return "technical"
        return "other"

    async def train(self, tenant_id: UUID | None = None) -> None:
        """Train the model on historical call data.

        Loads Call data with outcomes, extracts features, and trains
        a GradientBoostingClassifier from scikit-learn.
        """
        from sklearn.ensemble import GradientBoostingClassifier

        async with self._session_factory() as session:
            query = select(Call).where(Call.outcome.isnot(None))
            if tenant_id:
                query = query.where(Call.tenant_id == tenant_id)
            result = await session.execute(query)
            calls = result.scalars().all()

            if len(calls) < 10:
                logger.warning("Not enough training data (%d calls), skipping training", len(calls))
                self._is_trained = False
                return

            # Load leads for feature extraction
            lead_ids = [c.lead_id for c in calls]
            lead_result = await session.execute(
                select(Lead).where(Lead.id.in_(lead_ids))
            )
            leads = {l.id: l for l in lead_result.scalars().all()}

        X = []
        y = []
        for call in calls:
            lead = leads.get(call.lead_id)
            features = self._extract_features_from_call(call, lead)
            X.append(features)
            # Binary target: 1 if answered/qualified, 0 otherwise
            y.append(1 if call.outcome in (CallOutcome.qualified,) else 0)

        X_arr = np.array(X)
        y_arr = np.array(y)

        self._model = GradientBoostingClassifier(
            n_estimators=50,
            max_depth=3,
            random_state=42,
        )
        self._model.fit(X_arr, y_arr)
        self._is_trained = True
        logger.info("Timing predictor trained on %d samples", len(X))

    async def predict_best_times(self, lead_id: UUID) -> list[TimeSlot]:
        """Predict the best contact times for a given lead.

        Returns ranked TimeSlot list. If model is not trained, returns
        uniform distribution across business hours.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Lead).where(Lead.id == lead_id)
            )
            lead = result.scalar_one_or_none()

        if not self._is_trained or self._model is None:
            # Return uniform distribution over business hours
            slots = []
            for day in range(5):  # Mon-Fri
                for hour in range(9, 18):  # 9am-5pm
                    slots.append(
                        TimeSlot(
                            day_of_week=day,
                            hour=hour,
                            probability=1.0 / 45,  # uniform
                            timezone="UTC",
                        )
                    )
            return slots

        # Extract base features for the lead
        tz = "UTC"
        industry = "unknown"
        seniority = "other"
        if lead:
            if lead.enrichment_data:
                tz = lead.enrichment_data.get("timezone", "UTC")
                industry = lead.enrichment_data.get("industry", "unknown")
            if lead.title:
                seniority = self._classify_seniority(lead.title.lower())

        tz_encoded = self._encode_feature("timezone", tz)
        industry_encoded = self._encode_feature("industry", industry)
        seniority_encoded = self._encode_feature("seniority", seniority)

        # Predict probability for each hour of each weekday
        slots = []
        for day in range(7):
            for hour in range(24):
                features = np.array([[tz_encoded, industry_encoded, seniority_encoded, day, hour]])
                try:
                    prob = self._model.predict_proba(features)[0][1]
                except (IndexError, ValueError):
                    prob = 0.5
                slots.append(
                    TimeSlot(
                        day_of_week=day,
                        hour=hour,
                        probability=float(prob),
                        timezone=tz,
                    )
                )

        # Sort by probability descending
        slots.sort(key=lambda s: s.probability, reverse=True)
        return slots

    def predict_answer_probability(self, features: dict) -> float:
        """Raw prediction for given features dict.

        Args:
            features: dict with keys timezone, industry, seniority, day_of_week, hour

        Returns:
            Probability of answer (0.0-1.0)
        """
        if not self._is_trained or self._model is None:
            return 0.5

        tz_encoded = self._encode_feature("timezone", features.get("timezone", "UTC"))
        industry_encoded = self._encode_feature("industry", features.get("industry", "unknown"))
        seniority_encoded = self._encode_feature("seniority", features.get("seniority", "other"))
        day = features.get("day_of_week", 0)
        hour = features.get("hour", 9)

        X = np.array([[tz_encoded, industry_encoded, seniority_encoded, day, hour]])
        try:
            prob = self._model.predict_proba(X)[0][1]
            return float(prob)
        except (IndexError, ValueError):
            return 0.5
