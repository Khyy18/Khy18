"""Data quality monitoring for lead validation and enrichment quality scoring.

Provides validation of lead data, enrichment responses, duplicate detection,
and batch quality alerting. Used to ensure only high-quality data enters
the outreach pipeline.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Generic titles that indicate low-quality data
GENERIC_TITLES = {"employee", "n/a", "unknown", "staff", "worker", "team member"}

# Email validation regex pattern
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)

# Quality score weights
WEIGHT_EMAIL_VALID = 25.0
WEIGHT_COMPANY_PRESENT = 20.0
WEIGHT_TITLE_QUALITY = 20.0
WEIGHT_FIRST_NAME = 10.0
WEIGHT_LAST_NAME = 10.0
WEIGHT_PHONE = 5.0
WEIGHT_LINKEDIN = 10.0

# Thresholds
AUTO_REJECT_THRESHOLD = 30.0
BATCH_REJECT_ALERT_THRESHOLD = 0.5  # Alert if >50% rejected


class DataQualityMonitor:
    """Monitor and validate data quality for leads and enrichment results.

    Provides methods to validate individual leads, enrichment data,
    check for duplicates, and assess batch quality.
    """

    def __init__(self) -> None:
        """Initialize the DataQualityMonitor."""
        self._source_metrics: dict[str, dict[str, Any]] = {}

    def validate_lead(self, lead_data: dict) -> tuple[bool, float, list[str]]:
        """Validate lead data quality and compute a quality score.

        Args:
            lead_data: Dictionary containing lead fields (email, company,
                       title, first_name, last_name, phone, linkedin_url).

        Returns:
            Tuple of (is_valid, quality_score, issues) where is_valid is True
            if the lead passes minimum quality checks, quality_score is a float
            0-100, and issues is a list of validation problem descriptions.
        """
        issues: list[str] = []
        score = 0.0

        # Email validation (required)
        email = lead_data.get("email", "")
        if not email or not EMAIL_PATTERN.match(email):
            issues.append("Invalid or missing email address")
        else:
            score += WEIGHT_EMAIL_VALID

        # Company validation (required)
        company = lead_data.get("company", "")
        if not company or not company.strip():
            issues.append("Company name is empty")
        else:
            score += WEIGHT_COMPANY_PRESENT

        # Title validation
        title = lead_data.get("title", "")
        if not title or not title.strip():
            issues.append("Title is missing")
        elif title.strip().lower() in GENERIC_TITLES:
            issues.append(f"Generic title detected: '{title}'")
        else:
            score += WEIGHT_TITLE_QUALITY

        # Optional fields that improve score
        if lead_data.get("first_name", "").strip():
            score += WEIGHT_FIRST_NAME
        else:
            issues.append("First name is missing")

        if lead_data.get("last_name", "").strip():
            score += WEIGHT_LAST_NAME
        else:
            issues.append("Last name is missing")

        if lead_data.get("phone", "").strip():
            score += WEIGHT_PHONE

        if lead_data.get("linkedin_url", "").strip():
            score += WEIGHT_LINKEDIN

        # A lead is valid if it has a valid email, non-empty company, and non-generic title
        is_valid = (
            bool(email and EMAIL_PATTERN.match(email))
            and bool(company and company.strip())
            and bool(title and title.strip() and title.strip().lower() not in GENERIC_TITLES)
        )

        return is_valid, score, issues

    def validate_enrichment(
        self, enrichment_data: dict
    ) -> tuple[bool, float, list[str]]:
        """Validate enrichment data quality.

        Checks that enrichment responses contain meaningful data:
        at least one trigger event OR one talking point, and that
        company news is fresh (< 90 days old).

        Args:
            enrichment_data: Dictionary with enrichment fields
                (trigger_events, talking_points, company_news, news_date).

        Returns:
            Tuple of (is_valid, quality_score, issues).
        """
        issues: list[str] = []
        score = 0.0
        max_score = 100.0

        trigger_events = enrichment_data.get("trigger_events", [])
        talking_points = enrichment_data.get("talking_points", [])
        company_news = enrichment_data.get("company_news", [])
        news_date_str = enrichment_data.get("news_date")

        has_triggers = bool(trigger_events and len(trigger_events) > 0)
        has_talking_points = bool(talking_points and len(talking_points) > 0)

        if has_triggers:
            score += 40.0
        else:
            issues.append("No trigger events found")

        if has_talking_points:
            score += 40.0
        else:
            issues.append("No talking points found")

        # Check news freshness
        if company_news:
            score += 10.0
            if news_date_str:
                try:
                    news_date = datetime.fromisoformat(news_date_str)
                    if news_date.tzinfo is None:
                        news_date = news_date.replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - news_date
                    if age > timedelta(days=90):
                        issues.append("Company news is older than 90 days")
                        score -= 10.0
                    else:
                        score += 10.0
                except (ValueError, TypeError):
                    issues.append("Invalid news date format")
        else:
            issues.append("No company news available")

        # Valid if at least one of triggers or talking points exists
        is_valid = has_triggers or has_talking_points

        # Normalize score to 0-100
        score = max(0.0, min(max_score, score))

        return is_valid, score, issues

    async def check_duplicates(
        self, email: str, campaign_id: str, session: AsyncSession
    ) -> bool:
        """Check if a lead with the given email already exists in the campaign.

        Args:
            email: The email address to check.
            campaign_id: The campaign ID to check within.
            session: The async database session.

        Returns:
            True if a duplicate exists, False otherwise.
        """
        from core.models import Lead

        result = await session.execute(
            select(Lead).where(
                Lead.email == email,
                Lead.campaign_id == campaign_id,
            )
        )
        return result.scalar_one_or_none() is not None

    def get_source_metrics(self, source: str) -> dict:
        """Get quality metrics for a specific data source.

        Args:
            source: The data source name (e.g., 'apollo', 'hunter').

        Returns:
            Dictionary with quality metrics for the source.
        """
        if source not in self._source_metrics:
            self._source_metrics[source] = {
                "total_leads": 0,
                "valid_leads": 0,
                "rejected_leads": 0,
                "average_score": 0.0,
                "total_score": 0.0,
            }
        return self._source_metrics[source]

    def record_source_result(
        self, source: str, is_valid: bool, score: float
    ) -> None:
        """Record a validation result for source metrics tracking.

        Args:
            source: The data source name.
            is_valid: Whether the lead was valid.
            score: The quality score assigned.
        """
        metrics = self.get_source_metrics(source)
        metrics["total_leads"] += 1
        metrics["total_score"] += score
        if is_valid:
            metrics["valid_leads"] += 1
        else:
            metrics["rejected_leads"] += 1
        metrics["average_score"] = (
            metrics["total_score"] / metrics["total_leads"]
        )

    def should_auto_reject(self, quality_score: float) -> bool:
        """Determine if a lead should be automatically rejected.

        Args:
            quality_score: The computed quality score (0-100).

        Returns:
            True if the lead should be rejected (score < 30).
        """
        return quality_score < AUTO_REJECT_THRESHOLD

    def check_batch_quality(self, results: list[dict]) -> dict:
        """Check batch quality and generate alert if rejection rate is too high.

        Args:
            results: List of dicts with 'is_valid' and 'score' keys.

        Returns:
            Dictionary with batch metrics and alert status.
        """
        if not results:
            return {
                "total": 0,
                "valid": 0,
                "rejected": 0,
                "rejection_rate": 0.0,
                "average_score": 0.0,
                "alert": False,
                "alert_message": "",
            }

        total = len(results)
        rejected = sum(
            1 for r in results if not r.get("is_valid", True)
        )
        valid = total - rejected
        rejection_rate = rejected / total if total > 0 else 0.0
        avg_score = (
            sum(r.get("score", 0.0) for r in results) / total
            if total > 0
            else 0.0
        )

        alert = rejection_rate > BATCH_REJECT_ALERT_THRESHOLD
        alert_message = ""
        if alert:
            alert_message = (
                f"High rejection rate: {rejection_rate:.1%} "
                f"({rejected}/{total} leads rejected). "
                f"Average quality score: {avg_score:.1f}"
            )
            logger.warning("Batch quality alert: %s", alert_message)

        return {
            "total": total,
            "valid": valid,
            "rejected": rejected,
            "rejection_rate": rejection_rate,
            "average_score": avg_score,
            "alert": alert,
            "alert_message": alert_message,
        }
