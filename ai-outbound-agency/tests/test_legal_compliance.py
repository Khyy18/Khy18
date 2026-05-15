"""Tests for the GeoCompliance legal compliance module."""

import pytest

from compliance.legal import GeoCompliance


@pytest.fixture
def compliance() -> GeoCompliance:
    """Create a GeoCompliance instance for testing."""
    return GeoCompliance()


@pytest.fixture
def tenant_settings() -> dict:
    """Standard tenant settings with all required fields."""
    return {
        "company_name": "TestCo Inc",
        "physical_address": "123 Main St, San Francisco, CA 94102",
        "unsubscribe_url": "https://testco.com/unsubscribe",
        "data_processing_url": "https://testco.com/privacy",
    }


# --- Jurisdiction Detection Tests ---


class TestDetectJurisdiction:
    """Tests for jurisdiction detection from lead data."""

    def test_detect_jurisdiction_from_tld_de(self, compliance: GeoCompliance) -> None:
        """German TLD (.de) should map to EU/GDPR."""
        lead = {"email": "user@company.de", "enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "GDPR"

    def test_detect_jurisdiction_from_tld_fr(self, compliance: GeoCompliance) -> None:
        """French TLD (.fr) should map to EU/GDPR."""
        lead = {"email": "user@company.fr", "enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "GDPR"

    def test_detect_jurisdiction_from_tld_uk(self, compliance: GeoCompliance) -> None:
        """UK TLD (.uk) should map to UK/PECR."""
        lead = {"email": "user@company.co.uk", "enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "PECR"

    def test_detect_jurisdiction_from_tld_ca(self, compliance: GeoCompliance) -> None:
        """Canadian TLD (.ca) should map to CA/CASL."""
        lead = {"email": "user@company.ca", "enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "CASL"

    def test_detect_jurisdiction_from_tld_au(self, compliance: GeoCompliance) -> None:
        """Australian TLD (.au) should map to AU/SPAM_ACT."""
        lead = {"email": "user@company.com.au", "enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "SPAM_ACT"

    def test_detect_jurisdiction_from_tld_com(self, compliance: GeoCompliance) -> None:
        """Generic .com TLD should default to US/CAN-SPAM."""
        lead = {"email": "user@company.com", "enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "CAN-SPAM"

    def test_detect_jurisdiction_from_enrichment_germany(
        self, compliance: GeoCompliance
    ) -> None:
        """Country 'Germany' in enrichment data should map to EU/GDPR."""
        lead = {
            "email": "user@company.com",
            "enrichment_data": {
                "company_data": {"country": "Germany"}
            },
        }
        assert compliance.detect_jurisdiction(lead) == "GDPR"

    def test_detect_jurisdiction_from_enrichment_canada(
        self, compliance: GeoCompliance
    ) -> None:
        """Country 'Canada' in enrichment data should map to CA/CASL."""
        lead = {
            "email": "user@company.com",
            "enrichment_data": {
                "company_data": {"country": "Canada"}
            },
        }
        assert compliance.detect_jurisdiction(lead) == "CASL"

    def test_detect_jurisdiction_from_timezone_europe(
        self, compliance: GeoCompliance
    ) -> None:
        """European timezone should map to EU/GDPR."""
        lead = {
            "email": "",
            "timezone": "Europe/Berlin",
            "enrichment_data": {},
        }
        assert compliance.detect_jurisdiction(lead) == "GDPR"

    def test_detect_jurisdiction_from_timezone_canada(
        self, compliance: GeoCompliance
    ) -> None:
        """Canadian timezone should map to CA/CASL."""
        lead = {
            "email": "",
            "timezone": "America/Toronto",
            "enrichment_data": {},
        }
        assert compliance.detect_jurisdiction(lead) == "CASL"

    def test_detect_jurisdiction_enrichment_takes_priority(
        self, compliance: GeoCompliance
    ) -> None:
        """Enrichment country takes priority over TLD."""
        lead = {
            "email": "user@company.com",
            "enrichment_data": {
                "company_data": {"country": "France"}
            },
        }
        assert compliance.detect_jurisdiction(lead) == "GDPR"

    def test_detect_jurisdiction_empty_lead(self, compliance: GeoCompliance) -> None:
        """Empty lead data should default to CAN-SPAM."""
        lead = {"enrichment_data": {}}
        assert compliance.detect_jurisdiction(lead) == "CAN-SPAM"


# --- Compliance Requirements Tests ---


class TestGetComplianceRequirements:
    """Tests for compliance requirements lookup."""

    def test_requirements_us(self, compliance: GeoCompliance) -> None:
        """CAN-SPAM requires unsubscribe and physical address, no consent."""
        reqs = compliance.get_compliance_requirements("CAN-SPAM")
        assert reqs["requires_unsubscribe"] is True
        assert reqs["requires_physical_address"] is True
        assert reqs["requires_consent"] is False
        assert reqs["requires_legal_basis"] is False
        assert reqs["opt_out_type"] == "suppression"
        assert reqs["max_unsubscribe_days"] == 10

    def test_requirements_eu(self, compliance: GeoCompliance) -> None:
        """GDPR requires legal basis, data notice, and deletion on opt-out."""
        reqs = compliance.get_compliance_requirements("GDPR")
        assert reqs["requires_unsubscribe"] is True
        assert reqs["requires_physical_address"] is True
        assert reqs["requires_legal_basis"] is True
        assert reqs["requires_data_notice"] is True
        assert reqs["requires_consent"] is False
        assert reqs["opt_out_type"] == "deletion"

    def test_requirements_ca(self, compliance: GeoCompliance) -> None:
        """CASL requires consent and sender ID."""
        reqs = compliance.get_compliance_requirements("CASL")
        assert reqs["requires_unsubscribe"] is True
        assert reqs["requires_consent"] is True
        assert reqs["requires_sender_id"] is True
        assert reqs["opt_out_type"] == "suppression"
        assert reqs["max_unsubscribe_days"] == 10

    def test_requirements_uk(self, compliance: GeoCompliance) -> None:
        """PECR requires legal basis and data notice similar to GDPR."""
        reqs = compliance.get_compliance_requirements("PECR")
        assert reqs["requires_legal_basis"] is True
        assert reqs["requires_data_notice"] is True
        assert reqs["opt_out_type"] == "deletion"
        assert reqs["max_unsubscribe_days"] == 28

    def test_requirements_au(self, compliance: GeoCompliance) -> None:
        """SPAM_ACT requires consent and has short unsubscribe deadline."""
        reqs = compliance.get_compliance_requirements("SPAM_ACT")
        assert reqs["requires_consent"] is True
        assert reqs["requires_sender_id"] is True
        assert reqs["opt_out_type"] == "suppression"
        assert reqs["max_unsubscribe_days"] == 5

    def test_requirements_unknown_defaults_to_canspam(
        self, compliance: GeoCompliance
    ) -> None:
        """Unknown jurisdiction falls back to CAN-SPAM requirements."""
        reqs = compliance.get_compliance_requirements("UNKNOWN")
        assert reqs["requires_unsubscribe"] is True
        assert reqs["requires_physical_address"] is True


# --- Footer Generation Tests ---


class TestGenerateComplianceFooter:
    """Tests for compliance footer generation."""

    def test_generate_footer_us(
        self, compliance: GeoCompliance, tenant_settings: dict
    ) -> None:
        """US footer includes unsubscribe link and physical address."""
        footer = compliance.generate_compliance_footer("CAN-SPAM", tenant_settings)
        assert "Unsubscribe" in footer
        assert tenant_settings["physical_address"] in footer
        assert tenant_settings["company_name"] in footer
        # Should NOT have GDPR data processing notice
        assert "legitimate business interest" not in footer

    def test_generate_footer_eu(
        self, compliance: GeoCompliance, tenant_settings: dict
    ) -> None:
        """EU/GDPR footer includes data processing notice and right to object."""
        footer = compliance.generate_compliance_footer("GDPR", tenant_settings)
        assert "Unsubscribe" in footer
        assert "legitimate business interest" in footer
        assert "right to object" in footer
        assert "Data Processing Information" in footer
        assert tenant_settings["data_processing_url"] in footer

    def test_generate_footer_uk(
        self, compliance: GeoCompliance, tenant_settings: dict
    ) -> None:
        """UK/PECR footer includes data processing notice like GDPR."""
        footer = compliance.generate_compliance_footer("PECR", tenant_settings)
        assert "legitimate business interest" in footer
        assert "Data Processing Information" in footer


# --- Can Send Checks ---


class TestCheckCanSend:
    """Tests for the send eligibility check."""

    def test_check_can_send_blocks_missing_address(
        self, compliance: GeoCompliance
    ) -> None:
        """Blocks sending when physical address is missing (US/CAN-SPAM)."""
        lead = {"email": "user@company.com", "enrichment_data": {}}
        settings = {
            "company_name": "TestCo",
            "physical_address": "",
            "unsubscribe_url": "https://testco.com/unsub",
        }
        can_send, reason = compliance.check_can_send(lead, settings)
        assert can_send is False
        assert "physical address" in reason

    def test_check_can_send_blocks_missing_unsubscribe(
        self, compliance: GeoCompliance
    ) -> None:
        """Blocks sending when unsubscribe URL is missing."""
        lead = {"email": "user@company.com", "enrichment_data": {}}
        settings = {
            "company_name": "TestCo",
            "physical_address": "123 Main St",
            "unsubscribe_url": "",
        }
        can_send, reason = compliance.check_can_send(lead, settings)
        assert can_send is False
        assert "unsubscribe" in reason

    def test_check_can_send_blocks_gdpr_missing_data_url(
        self, compliance: GeoCompliance
    ) -> None:
        """Blocks EU/GDPR sending when data processing URL is missing."""
        lead = {
            "email": "user@company.de",
            "enrichment_data": {},
        }
        settings = {
            "company_name": "TestCo",
            "physical_address": "123 Main St",
            "unsubscribe_url": "https://testco.com/unsub",
            "data_processing_url": "",
        }
        can_send, reason = compliance.check_can_send(lead, settings)
        assert can_send is False
        assert "data processing" in reason

    def test_check_can_send_blocks_casl_no_consent(
        self, compliance: GeoCompliance
    ) -> None:
        """Blocks CASL sending when consent is not recorded."""
        lead = {
            "email": "user@company.ca",
            "enrichment_data": {},
        }
        settings = {
            "company_name": "TestCo",
            "physical_address": "123 Main St",
            "unsubscribe_url": "https://testco.com/unsub",
            "data_processing_url": "https://testco.com/privacy",
        }
        can_send, reason = compliance.check_can_send(lead, settings)
        assert can_send is False
        assert "consent" in reason

    def test_check_can_send_allows_complete(
        self, compliance: GeoCompliance, tenant_settings: dict
    ) -> None:
        """Allows sending when all required fields are present (US)."""
        lead = {"email": "user@company.com", "enrichment_data": {}}
        can_send, reason = compliance.check_can_send(lead, tenant_settings)
        assert can_send is True
        assert reason == "compliant"

    def test_check_can_send_allows_gdpr_complete(
        self, compliance: GeoCompliance, tenant_settings: dict
    ) -> None:
        """Allows GDPR sending when all required fields are present."""
        lead = {"email": "user@company.de", "enrichment_data": {}}
        can_send, reason = compliance.check_can_send(lead, tenant_settings)
        assert can_send is True
        assert reason == "compliant"

    def test_check_can_send_allows_casl_with_consent(
        self, compliance: GeoCompliance, tenant_settings: dict
    ) -> None:
        """Allows CASL sending when consent is recorded."""
        lead = {
            "email": "user@company.ca",
            "enrichment_data": {},
            "consent": True,
        }
        can_send, reason = compliance.check_can_send(lead, tenant_settings)
        assert can_send is True
        assert reason == "compliant"


# --- Opt-Out Handling ---


class TestHandleOptOut:
    """Tests for opt-out handling per jurisdiction."""

    def test_opt_out_gdpr_deletes(self, compliance: GeoCompliance) -> None:
        """GDPR opt-out returns deletion instructions."""
        lead = {"id": "lead-123", "email": "user@company.de"}
        result = compliance.handle_opt_out(lead, "GDPR")
        assert result["action"] == "delete"
        assert "Delete all personal data" in result["description"]
        assert "Delete enrichment data" in result["steps"]
        assert "Delete message history" in result["steps"]

    def test_opt_out_canspam_suppresses(self, compliance: GeoCompliance) -> None:
        """CAN-SPAM opt-out returns suppression instructions."""
        lead = {"id": "lead-456", "email": "user@company.com"}
        result = compliance.handle_opt_out(lead, "CAN-SPAM")
        assert result["action"] == "suppress"
        assert "suppression list" in result["description"]
        assert "Add to suppression list" in result["steps"]
        assert "Retain records for compliance audit" in result["steps"]

    def test_opt_out_pecr_deletes(self, compliance: GeoCompliance) -> None:
        """PECR opt-out returns deletion instructions like GDPR."""
        lead = {"id": "lead-789", "email": "user@company.co.uk"}
        result = compliance.handle_opt_out(lead, "PECR")
        assert result["action"] == "delete"


# --- Audit Record ---


class TestRecordComplianceAudit:
    """Tests for compliance audit record creation."""

    def test_compliance_audit_record(self, compliance: GeoCompliance) -> None:
        """Audit record contains all required fields with timestamp."""
        record = compliance.record_compliance_audit(
            lead_id="lead-123",
            jurisdiction="GDPR",
            legal_basis="legitimate_interest",
            action="email_sent",
        )
        assert record["lead_id"] == "lead-123"
        assert record["jurisdiction"] == "GDPR"
        assert record["legal_basis"] == "legitimate_interest"
        assert record["action"] == "email_sent"
        assert "timestamp" in record
        # Timestamp should be ISO format
        assert "T" in record["timestamp"]
