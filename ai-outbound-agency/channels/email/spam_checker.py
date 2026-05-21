"""Spam Scoring Pre-Send - pure Python spam scoring engine for outbound emails."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Spam trigger words with weights
SPAM_TRIGGER_WORDS: dict[str, int] = {
    "free": 1,
    "guarantee": 2,
    "urgent": 3,
    "act now": 3,
    "limited time": 2,
    "click here": 2,
    "winner": 3,
    "congratulations": 2,
    "no obligation": 2,
    "risk free": 2,
}


@dataclass
class CheckResult:
    """Result of a single spam check."""

    name: str
    score: float
    detail: str


@dataclass
class SpamCheckResult:
    """Complete spam check result."""

    score: float
    verdict: str
    breakdown: list[CheckResult] = field(default_factory=list)


class SpamChecker:
    """Pure Python spam scoring engine for pre-send email validation.

    Performs fast (<50ms) content-based scoring without external API calls.
    """

    def __init__(self) -> None:
        self._trigger_words = SPAM_TRIGGER_WORDS

    def check_message(
        self,
        subject: str,
        html_body: str,
        from_domain: str | None = None,
    ) -> SpamCheckResult:
        """Score an email message for spam risk.

        Args:
            subject: Email subject line.
            html_body: HTML body content of the email.
            from_domain: Optional sending domain for domain-level checks.

        Returns:
            SpamCheckResult with score, verdict, and breakdown.
        """
        breakdown: list[CheckResult] = []

        # 1. Spam trigger words
        result = self._check_trigger_words(subject, html_body)
        if result:
            breakdown.append(result)

        # 2. ALL CAPS subject
        result = self._check_caps_subject(subject)
        if result:
            breakdown.append(result)

        # 3. Excessive punctuation
        result = self._check_excessive_punctuation(subject, html_body)
        if result:
            breakdown.append(result)

        # 4. HTML/text ratio
        result = self._check_html_ratio(html_body)
        if result:
            breakdown.append(result)

        # 5. Link density
        result = self._check_link_density(html_body)
        if result:
            breakdown.append(result)

        # 6. Image-to-text ratio
        result = self._check_image_ratio(html_body)
        if result:
            breakdown.append(result)

        # 7. Unsubscribe link (bonus)
        result = self._check_unsubscribe(html_body)
        if result:
            breakdown.append(result)

        # 8. Personalization tokens (bonus)
        result = self._check_personalization(subject, html_body)
        if result:
            breakdown.append(result)

        # 9. Short subject line (bonus)
        result = self._check_short_subject(subject)
        if result:
            breakdown.append(result)

        total_score = sum(check.score for check in breakdown)
        # Score cannot go below 0
        total_score = max(0.0, total_score)

        if total_score > 5:
            verdict = "blocked"
        elif total_score >= 3:
            verdict = "warning"
        else:
            verdict = "send"

        return SpamCheckResult(score=total_score, verdict=verdict, breakdown=breakdown)

    def _check_trigger_words(self, subject: str, html_body: str) -> CheckResult | None:
        """Check for spam trigger words in subject and body."""
        text = f"{subject} {self._strip_html(html_body)}".lower()
        total_weight = 0
        found_words: list[str] = []

        for word, weight in self._trigger_words.items():
            if word in text:
                total_weight += weight
                found_words.append(word)

        if total_weight > 0:
            return CheckResult(
                name="spam_trigger_words",
                score=total_weight,
                detail=f"Found trigger words: {', '.join(found_words)}",
            )
        return None

    def _check_caps_subject(self, subject: str) -> CheckResult | None:
        """Check if subject is mostly uppercase."""
        alpha_chars = [c for c in subject if c.isalpha()]
        if not alpha_chars:
            return None

        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.5:
            return CheckResult(
                name="all_caps_subject",
                score=3,
                detail=f"Subject is {upper_ratio:.0%} uppercase",
            )
        return None

    def _check_excessive_punctuation(self, subject: str, html_body: str) -> CheckResult | None:
        """Check for excessive punctuation (!!!, ???, etc.)."""
        text = f"{subject} {self._strip_html(html_body)}"
        pattern = r"[!]{2,}|[?]{2,}|[!?]{2,}"
        matches = re.findall(pattern, text)
        if matches:
            return CheckResult(
                name="excessive_punctuation",
                score=2,
                detail=f"Found excessive punctuation: {len(matches)} occurrence(s)",
            )
        return None

    def _check_html_ratio(self, html_body: str) -> CheckResult | None:
        """Check HTML tag to text ratio."""
        if not html_body:
            return None

        tags = re.findall(r"<[^>]+>", html_body)
        tag_chars = sum(len(tag) for tag in tags)
        total_chars = len(html_body)

        if total_chars == 0:
            return None

        html_ratio = tag_chars / total_chars
        if html_ratio > 0.6:
            return CheckResult(
                name="high_html_ratio",
                score=2,
                detail=f"HTML tags make up {html_ratio:.0%} of content",
            )
        return None

    def _check_link_density(self, html_body: str) -> CheckResult | None:
        """Check link density (links per 100 words)."""
        links = re.findall(r"<a\s", html_body, re.IGNORECASE)
        text = self._strip_html(html_body)
        words = text.split()
        word_count = len(words) if words else 1

        links_per_100 = (len(links) / word_count) * 100
        if links_per_100 > 3:
            return CheckResult(
                name="high_link_density",
                score=2,
                detail=f"Link density: {links_per_100:.1f} links per 100 words",
            )
        return None

    def _check_image_ratio(self, html_body: str) -> CheckResult | None:
        """Check for heavy image usage."""
        img_tags = re.findall(r"<img\s", html_body, re.IGNORECASE)
        if len(img_tags) > 3:
            return CheckResult(
                name="heavy_images",
                score=1,
                detail=f"Found {len(img_tags)} images",
            )
        return None

    def _check_unsubscribe(self, html_body: str) -> CheckResult | None:
        """Check for unsubscribe link (bonus for good practice)."""
        text_lower = html_body.lower()
        if "unsubscribe" in text_lower:
            return CheckResult(
                name="unsubscribe_present",
                score=-3,
                detail="Unsubscribe link found (good practice)",
            )
        return None

    def _check_personalization(self, subject: str, html_body: str) -> CheckResult | None:
        """Check for personalization tokens."""
        text = f"{subject} {html_body}"
        # Match {{first_name}}, {first_name}, or common personalized greetings
        patterns = [
            r"\{\{[\w_]+\}\}",
            r"\{[\w_]+\}",
            r"(?i)\bHi\s+[A-Z][a-z]+",
            r"(?i)\bHello\s+[A-Z][a-z]+",
            r"(?i)\bDear\s+[A-Z][a-z]+",
        ]
        for pattern in patterns:
            if re.search(pattern, text):
                return CheckResult(
                    name="personalization_present",
                    score=-2,
                    detail="Personalization tokens detected (good practice)",
                )
        return None

    def _check_short_subject(self, subject: str) -> CheckResult | None:
        """Check for short subject line (bonus)."""
        if len(subject) < 50:
            return CheckResult(
                name="short_subject",
                score=-1,
                detail=f"Subject length {len(subject)} chars (concise)",
            )
        return None

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags from content to get plain text."""
        return re.sub(r"<[^>]+>", " ", html)

    async def verify_domain_auth(self, domain: str) -> dict[str, Any]:
        """Pre-flight DNS check to verify SPF/DKIM/DMARC for a domain.

        Reuses the dns.resolver pattern from BounceMonitor.

        Args:
            domain: The sending domain to verify.

        Returns:
            Dict with spf, dkim, and dmarc status.
        """
        import dns.resolver

        result: dict[str, Any] = {
            "spf": {"found": False, "record": None},
            "dkim": {"found": False, "record": None},
            "dmarc": {"found": False, "record": None},
            "all_passed": False,
        }

        # Check SPF (TXT record with v=spf1)
        try:
            answers = dns.resolver.resolve(domain, "TXT")
            for rdata in answers:
                txt_value = rdata.to_text().strip('"')
                if txt_value.startswith("v=spf1"):
                    result["spf"] = {"found": True, "record": txt_value}
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception):
            pass

        # Check DKIM (selector._domainkey.domain TXT)
        dkim_domain = f"selector1._domainkey.{domain}"
        try:
            answers = dns.resolver.resolve(dkim_domain, "TXT")
            for rdata in answers:
                txt_value = rdata.to_text().strip('"')
                if "v=DKIM1" in txt_value or "k=" in txt_value:
                    result["dkim"] = {"found": True, "record": txt_value}
                    break
            if not result["dkim"]["found"] and answers:
                txt_value = answers[0].to_text().strip('"')
                result["dkim"] = {"found": True, "record": txt_value}
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception):
            pass

        # Check DMARC (_dmarc.domain TXT)
        dmarc_domain = f"_dmarc.{domain}"
        try:
            answers = dns.resolver.resolve(dmarc_domain, "TXT")
            for rdata in answers:
                txt_value = rdata.to_text().strip('"')
                if txt_value.startswith("v=DMARC1"):
                    result["dmarc"] = {"found": True, "record": txt_value}
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception):
            pass

        result["all_passed"] = all(
            result[key]["found"] for key in ("spf", "dkim", "dmarc")
        )

        return result
