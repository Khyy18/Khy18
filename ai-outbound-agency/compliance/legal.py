"""Geo-aware legal compliance manager for outbound messaging."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Jurisdiction mapping by country
JURISDICTIONS: dict[str, str] = {
    "US": "CAN-SPAM",
    "EU": "GDPR",
    "CA": "CASL",
    "UK": "PECR",
    "AU": "SPAM_ACT",
    "DEFAULT": "CAN-SPAM",
}

# EU member state country names for detection
_EU_COUNTRIES: set[str] = {
    "Germany", "France", "Italy", "Spain", "Netherlands", "Belgium",
    "Austria", "Sweden", "Denmark", "Finland", "Ireland", "Portugal",
    "Greece", "Poland", "Czech Republic", "Romania", "Hungary",
    "Bulgaria", "Croatia", "Slovakia", "Slovenia", "Estonia",
    "Latvia", "Lithuania", "Luxembourg", "Malta", "Cyprus",
}

# TLD to jurisdiction mapping
_TLD_TO_JURISDICTION: dict[str, str] = {
    ".de": "EU", ".fr": "EU", ".it": "EU", ".es": "EU", ".nl": "EU",
    ".be": "EU", ".at": "EU", ".se": "EU", ".dk": "EU", ".fi": "EU",
    ".ie": "EU", ".pt": "EU", ".gr": "EU", ".pl": "EU", ".cz": "EU",
    ".ro": "EU", ".hu": "EU", ".bg": "EU", ".hr": "EU", ".sk": "EU",
    ".si": "EU", ".ee": "EU", ".lv": "EU", ".lt": "EU", ".lu": "EU",
    ".mt": "EU", ".cy": "EU", ".eu": "EU",
    ".uk": "UK", ".co.uk": "UK",
    ".ca": "CA",
    ".au": "AU", ".com.au": "AU",
    ".us": "US",
}

# Timezone prefix to jurisdiction mapping
_TIMEZONE_TO_JURISDICTION: dict[str, str] = {
    "Europe/": "EU",
    "America/Toronto": "CA",
    "America/Vancouver": "CA",
    "America/Montreal": "CA",
    "America/Edmonton": "CA",
    "America/Winnipeg": "CA",
    "America/Halifax": "CA",
    "Australia/": "AU",
    "Pacific/Auckland": "AU",
}


class GeoCompliance:
    """Geo-aware legal compliance manager for outbound messaging."""

    JURISDICTIONS = JURISDICTIONS

    def detect_jurisdiction(self, lead_data: dict[str, Any]) -> str:
        """Determine jurisdiction from lead enrichment data.

        Detection priority:
        1. Enrichment data country field
        2. Email domain TLD
        3. Timezone

        Args:
            lead_data: Lead dict with enrichment_data, email, and timezone fields.

        Returns:
            Jurisdiction string (e.g., "CAN-SPAM", "GDPR", "CASL", "PECR", "SPAM_ACT").
        """
        # 1. Check enrichment data for country
        enrichment = lead_data.get("enrichment_data", {})
        company_data = enrichment.get("company_data", {})
        country = company_data.get("country", "")

        if country:
            jurisdiction = self._country_to_jurisdiction(country)
            if jurisdiction:
                return jurisdiction

        # 2. Check email domain TLD
        email = lead_data.get("email", "")
        if email and "@" in email:
            domain = email.split("@")[1].lower()
            jurisdiction = self._tld_to_jurisdiction(domain)
            if jurisdiction:
                return jurisdiction

        # 3. Check timezone
        tz = lead_data.get("timezone", "") or enrichment.get("timezone", "")
        if tz:
            jurisdiction = self._timezone_to_jurisdiction(tz)
            if jurisdiction:
                return JURISDICTIONS.get(jurisdiction, JURISDICTIONS["DEFAULT"])

        return JURISDICTIONS["DEFAULT"]

    def get_compliance_requirements(self, jurisdiction: str) -> dict[str, Any]:
        """Return compliance requirements for a given jurisdiction.

        Args:
            jurisdiction: One of CAN-SPAM, GDPR, CASL, PECR, SPAM_ACT.

        Returns:
            Dict with compliance requirement flags and values.
        """
        requirements: dict[str, dict[str, Any]] = {
            "CAN-SPAM": {
                "requires_unsubscribe": True,
                "requires_physical_address": True,
                "requires_sender_id": True,
                "requires_legal_basis": False,
                "requires_data_notice": False,
                "requires_consent": False,
                "opt_out_type": "suppression",
                "max_unsubscribe_days": 10,
            },
            "GDPR": {
                "requires_unsubscribe": True,
                "requires_physical_address": True,
                "requires_sender_id": True,
                "requires_legal_basis": True,
                "requires_data_notice": True,
                "requires_consent": False,
                "opt_out_type": "deletion",
                "max_unsubscribe_days": 30,
            },
            "CASL": {
                "requires_unsubscribe": True,
                "requires_physical_address": True,
                "requires_sender_id": True,
                "requires_legal_basis": False,
                "requires_data_notice": False,
                "requires_consent": True,
                "opt_out_type": "suppression",
                "max_unsubscribe_days": 10,
            },
            "PECR": {
                "requires_unsubscribe": True,
                "requires_physical_address": True,
                "requires_sender_id": True,
                "requires_legal_basis": True,
                "requires_data_notice": True,
                "requires_consent": False,
                "opt_out_type": "deletion",
                "max_unsubscribe_days": 28,
            },
            "SPAM_ACT": {
                "requires_unsubscribe": True,
                "requires_physical_address": True,
                "requires_sender_id": True,
                "requires_legal_basis": False,
                "requires_data_notice": False,
                "requires_consent": True,
                "opt_out_type": "suppression",
                "max_unsubscribe_days": 5,
            },
        }

        return requirements.get(jurisdiction, requirements["CAN-SPAM"])

    def generate_compliance_footer(
        self, jurisdiction: str, tenant_settings: dict[str, Any]
    ) -> str:
        """Generate an HTML compliance footer based on jurisdiction requirements.

        Args:
            jurisdiction: The applicable jurisdiction.
            tenant_settings: Dict with company_name, physical_address,
                unsubscribe_url, data_processing_url.

        Returns:
            HTML string with the compliance footer.
        """
        company_name = tenant_settings.get("company_name", "")
        physical_address = tenant_settings.get("physical_address", "")
        unsubscribe_url = tenant_settings.get("unsubscribe_url", "")
        data_processing_url = tenant_settings.get("data_processing_url", "")

        parts: list[str] = ['<div style="font-size:11px;color:#666;margin-top:20px;">']

        # Sender identification
        if company_name:
            parts.append(f"<p>Sent by {html.escape(company_name)}</p>")

        # Physical address (required by CAN-SPAM, GDPR, CASL, PECR, SPAM_ACT)
        if physical_address:
            parts.append(f"<p>{html.escape(physical_address)}</p>")

        # Unsubscribe link (required by all)
        if unsubscribe_url:
            escaped_url = html.escape(unsubscribe_url, quote=True)
            parts.append(
                f'<p><a href="{escaped_url}">Unsubscribe</a></p>'
            )

        # GDPR / PECR specific: data processing notice and right to object
        if jurisdiction in ("GDPR", "PECR"):
            parts.append(
                "<p>This email is sent on the basis of legitimate business interest. "
                "You have the right to object to this processing.</p>"
            )
            if data_processing_url:
                escaped_dp_url = html.escape(data_processing_url, quote=True)
                parts.append(
                    f'<p><a href="{escaped_dp_url}">Data Processing Information</a></p>'
                )

        parts.append("</div>")
        return "\n".join(parts)

    def check_can_send(
        self, lead_data: dict[str, Any], tenant_settings: dict[str, Any]
    ) -> tuple[bool, str]:
        """Check whether an email can be sent to this lead given compliance rules.

        Args:
            lead_data: Lead dict with enrichment_data and consent fields.
            tenant_settings: Dict with company_name, physical_address,
                unsubscribe_url, data_processing_url.

        Returns:
            Tuple of (can_send: bool, reason: str).
        """
        jurisdiction = self.detect_jurisdiction(lead_data)
        requirements = self.get_compliance_requirements(jurisdiction)

        # Check required tenant settings
        if requirements["requires_physical_address"]:
            if not tenant_settings.get("physical_address"):
                return False, f"{jurisdiction} requires a physical address in emails"

        if requirements["requires_data_notice"]:
            if not tenant_settings.get("data_processing_url"):
                return False, f"{jurisdiction} requires a data processing notice URL"

        if not tenant_settings.get("unsubscribe_url"):
            return False, f"{jurisdiction} requires an unsubscribe mechanism"

        # Check consent requirement
        if requirements["requires_consent"]:
            consent = lead_data.get("consent") or lead_data.get(
                "enrichment_data", {}
            ).get("consent")
            if not consent:
                return False, f"{jurisdiction} requires prior consent to send"

        return True, "compliant"

    def record_compliance_audit(
        self,
        lead_id: str,
        jurisdiction: str,
        legal_basis: str,
        action: str,
    ) -> dict[str, Any]:
        """Record a compliance audit entry.

        Args:
            lead_id: The lead identifier.
            jurisdiction: The applicable jurisdiction.
            legal_basis: The legal basis for processing (e.g., legitimate interest).
            action: The action taken (e.g., email_sent, opt_out_processed).

        Returns:
            Audit record dict with all fields and timestamp.
        """
        record = {
            "lead_id": lead_id,
            "jurisdiction": jurisdiction,
            "legal_basis": legal_basis,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Compliance audit: %s", record)
        return record

    def handle_opt_out(
        self, lead_data: dict[str, Any], jurisdiction: str
    ) -> dict[str, Any]:
        """Return opt-out handling instructions based on jurisdiction.

        Args:
            lead_data: Lead dict with identifiers.
            jurisdiction: The applicable jurisdiction.

        Returns:
            Dict with opt-out handling instructions.
        """
        requirements = self.get_compliance_requirements(jurisdiction)
        opt_out_type = requirements["opt_out_type"]

        if opt_out_type == "deletion":
            return {
                "action": "delete",
                "description": "Delete all personal data per GDPR/PECR right to erasure",
                "lead_id": lead_data.get("id", ""),
                "email": lead_data.get("email", ""),
                "steps": [
                    "Remove from all active sequences",
                    "Delete enrichment data",
                    "Delete message history",
                    "Add to permanent suppression list",
                    "Confirm deletion to data subject",
                ],
            }
        else:
            return {
                "action": "suppress",
                "description": "Add to suppression list per CAN-SPAM/CASL/SPAM_ACT",
                "lead_id": lead_data.get("id", ""),
                "email": lead_data.get("email", ""),
                "steps": [
                    "Remove from all active sequences",
                    "Add to suppression list",
                    "Retain records for compliance audit",
                ],
            }

    # -- Private helpers --

    def _country_to_jurisdiction(self, country: str) -> str | None:
        """Map a country name to its jurisdiction."""
        country_lower = country.lower().strip()

        # Direct mappings
        if country_lower in ("united states", "usa", "us"):
            return JURISDICTIONS["US"]
        if country_lower in ("canada",):
            return JURISDICTIONS["CA"]
        if country_lower in ("united kingdom", "uk", "great britain"):
            return JURISDICTIONS["UK"]
        if country_lower in ("australia",):
            return JURISDICTIONS["AU"]

        # Check EU countries
        for eu_country in _EU_COUNTRIES:
            if country_lower == eu_country.lower():
                return JURISDICTIONS["EU"]

        return None

    def _tld_to_jurisdiction(self, domain: str) -> str | None:
        """Map an email domain to its jurisdiction based on TLD."""
        # Check multi-part TLDs first (e.g., .co.uk, .com.au)
        for tld, jurisdiction_key in _TLD_TO_JURISDICTION.items():
            if domain.endswith(tld):
                return JURISDICTIONS.get(jurisdiction_key, JURISDICTIONS["DEFAULT"])

        # Generic TLDs default to US
        generic_tlds = (".com", ".org", ".net", ".io", ".co")
        for tld in generic_tlds:
            if domain.endswith(tld) and not domain.endswith(".co.uk"):
                return JURISDICTIONS["US"]

        return None

    def _timezone_to_jurisdiction(self, tz: str) -> str | None:
        """Map a timezone string to a jurisdiction key."""
        # Check exact matches first
        if tz in _TIMEZONE_TO_JURISDICTION:
            return _TIMEZONE_TO_JURISDICTION[tz]

        # Check prefix matches
        for prefix, jurisdiction_key in _TIMEZONE_TO_JURISDICTION.items():
            if prefix.endswith("/") and tz.startswith(prefix):
                return jurisdiction_key

        # US timezones
        us_prefixes = ("America/New_York", "America/Chicago", "America/Denver",
                       "America/Los_Angeles", "America/Phoenix", "US/")
        for prefix in us_prefixes:
            if tz.startswith(prefix) or tz == prefix:
                return "US"

        return None
