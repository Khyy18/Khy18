"""Auto-Approve Engine - evaluates proposed responses against safety criteria."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agents.reply_quality import ReplyQualityScorer
from core.config import Settings
from core.llm import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AutoApproveResult:
    """Result of auto-approve evaluation."""

    approved: bool
    reason: str
    quality_score: int
    safety_checks: dict[str, bool] = field(default_factory=dict)
    should_regenerate: bool = False
    audit_log: dict[str, Any] = field(default_factory=dict)


# Basic profanity word list for safety checking
_PROFANITY_WORDS = [
    "damn", "hell", "shit", "fuck", "ass", "bastard", "crap",
    "dick", "bitch", "piss", "idiot", "stupid", "moron",
]

# Pricing-related patterns
_PRICING_PATTERN = re.compile(
    r"\$\d|price|pricing|discount|% off|percent off|cost\s",
    re.IGNORECASE,
)

# Timeline commitment patterns
_TIMELINE_PATTERN = re.compile(
    r"by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|within\s+\d+\s+days?"
    r"|deliver\s+by"
    r"|deadline"
    r"|\beta\b"
    r"|by\s+end\s+of",
    re.IGNORECASE,
)


class AutoApproveEngine:
    """Evaluates proposed responses against safety criteria for auto-approval."""

    def __init__(self, llm_client: LLMClient, settings: Settings) -> None:
        self._llm = llm_client
        self._settings = settings
        self._quality_scorer = ReplyQualityScorer(llm_client)

    async def evaluate(
        self,
        proposed_response: dict[str, Any],
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> AutoApproveResult:
        """Evaluate a proposed response for auto-approval.

        Args:
            proposed_response: Dict with subject, body, action keys.
            lead_data: Information about the lead (first_name, last_name, company, etc).
            campaign_context: Campaign details for context.

        Returns:
            AutoApproveResult with approval decision and details.
        """
        text = proposed_response.get("body", "")
        lead_company = lead_data.get("company", "")

        # Load competitor list from campaign context
        competitors = campaign_context.get("competitors", [])

        # Run all safety checks
        safety_checks = {
            "no_pricing_promises": self._check_no_pricing_promises(text),
            "no_timeline_commitments": self._check_no_timeline_commitments(text),
            "no_competitor_mentions": self._check_no_competitor_mentions(text, competitors),
            "word_limit": self._check_word_limit(text),
            "no_profanity": self._check_no_profanity(text),
            "not_protected_company": self._check_protected_company(lead_company),
        }

        all_safety_passed = all(safety_checks.values())

        # Get quality score
        quality_result = await self._quality_scorer.score_response(
            response_text=text,
            prospect_message=lead_data.get("original_message", ""),
            campaign_context=campaign_context,
        )
        quality_score = quality_result.overall_score
        threshold = self._settings.auto_approve_quality_threshold

        # Decision logic
        if all_safety_passed and quality_score >= threshold:
            result = AutoApproveResult(
                approved=True,
                reason="All safety checks passed and quality score meets threshold",
                quality_score=quality_score,
                safety_checks=safety_checks,
                should_regenerate=False,
            )
        elif all_safety_passed and 60 <= quality_score < threshold:
            result = AutoApproveResult(
                approved=False,
                reason=f"Quality score {quality_score} below threshold {threshold}, regeneration recommended",
                quality_score=quality_score,
                safety_checks=safety_checks,
                should_regenerate=True,
            )
        else:
            failed_checks = [k for k, v in safety_checks.items() if not v]
            reason_parts = []
            if not all_safety_passed:
                reason_parts.append(f"Safety checks failed: {', '.join(failed_checks)}")
            if quality_score < 60:
                reason_parts.append(f"Quality score {quality_score} below minimum (60)")
            result = AutoApproveResult(
                approved=False,
                reason="; ".join(reason_parts) if reason_parts else "Did not meet approval criteria",
                quality_score=quality_score,
                safety_checks=safety_checks,
                should_regenerate=False,
            )

        # Build audit log
        result.audit_log = {
            "quality_score": quality_score,
            "threshold": threshold,
            "safety_checks": safety_checks,
            "all_safety_passed": all_safety_passed,
            "approved": result.approved,
            "should_regenerate": result.should_regenerate,
            "reason": result.reason,
            "lead_company": lead_company,
        }

        self._log_decision(result)
        return result

    def _check_no_pricing_promises(self, text: str) -> bool:
        """Check that text does not contain pricing promises.

        Returns True if text is safe (no pricing mentions).
        """
        return _PRICING_PATTERN.search(text) is None

    def _check_no_timeline_commitments(self, text: str) -> bool:
        """Check that text does not contain timeline commitments.

        Returns True if text is safe (no timeline commitments).
        """
        return _TIMELINE_PATTERN.search(text) is None

    def _check_no_competitor_mentions(self, text: str, competitors: list[str]) -> bool:
        """Check that text does not mention any competitors.

        Returns True if text is safe (no competitor mentions).
        """
        if not competitors:
            return True
        text_lower = text.lower()
        for competitor in competitors:
            if competitor.lower() in text_lower:
                return False
        return True

    def _check_word_limit(self, text: str, max_words: int = 300) -> bool:
        """Check that text is within word limit.

        Returns True if text is within the limit.
        """
        word_count = len(text.split())
        return word_count <= max_words

    def _check_no_profanity(self, text: str) -> bool:
        """Check that text does not contain profanity.

        Returns True if text is safe (no profanity).
        """
        text_lower = text.lower()
        for word in _PROFANITY_WORDS:
            # Use word boundary matching
            if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
                return False
        return True

    def _check_protected_company(self, lead_company: str) -> bool:
        """Check that lead company is not in the protected companies list.

        Returns True if company is NOT protected (safe to auto-approve).
        """
        if not lead_company:
            return True
        try:
            protected = json.loads(self._settings.protected_companies_list)
        except (json.JSONDecodeError, TypeError):
            protected = []
        lead_company_lower = lead_company.lower()
        for company in protected:
            if company.lower() == lead_company_lower:
                return False
        return True

    def _log_decision(self, result: AutoApproveResult) -> None:
        """Log the auto-approve decision with structured details.

        TODO: Persist audit logs to a database table in a future iteration.
        Currently audit_log data is only logged at INFO level and lost on
        log rotation. A dedicated audit_decisions table should store these
        records for compliance and ML training purposes.
        """
        logger.info(
            "Auto-approve decision: approved=%s, reason=%s, quality_score=%d, "
            "safety_checks=%s, should_regenerate=%s",
            result.approved,
            result.reason,
            result.quality_score,
            result.safety_checks,
            result.should_regenerate,
        )
