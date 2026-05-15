"""Tests for the data quality monitor."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from data.quality_monitor import DataQualityMonitor


@pytest.fixture
def monitor():
    """Create a DataQualityMonitor instance."""
    return DataQualityMonitor()


class TestLeadValidation:
    """Tests for lead validation."""

    def test_valid_lead_passes(self, monitor: DataQualityMonitor):
        """Test that a valid lead passes validation with a high score."""
        lead_data = {
            "email": "john.doe@example.com",
            "company": "Acme Inc",
            "title": "VP of Engineering",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+1-555-0123",
            "linkedin_url": "https://linkedin.com/in/johndoe",
        }

        is_valid, score, issues = monitor.validate_lead(lead_data)

        assert is_valid is True
        assert score == 100.0
        assert issues == []

    def test_invalid_email_rejected(self, monitor: DataQualityMonitor):
        """Test that a lead with invalid email is rejected."""
        lead_data = {
            "email": "not-an-email",
            "company": "Acme Inc",
            "title": "VP of Engineering",
            "first_name": "John",
            "last_name": "Doe",
        }

        is_valid, score, issues = monitor.validate_lead(lead_data)

        assert is_valid is False
        assert "Invalid or missing email address" in issues

    def test_empty_email_rejected(self, monitor: DataQualityMonitor):
        """Test that a lead with empty email is rejected."""
        lead_data = {
            "email": "",
            "company": "Acme Inc",
            "title": "Engineer",
            "first_name": "John",
            "last_name": "Doe",
        }

        is_valid, score, issues = monitor.validate_lead(lead_data)

        assert is_valid is False
        assert "Invalid or missing email address" in issues

    def test_generic_title_rejected(self, monitor: DataQualityMonitor):
        """Test that leads with generic titles are rejected."""
        generic_titles = ["Employee", "N/A", "Unknown", "Staff", "worker"]

        for title in generic_titles:
            lead_data = {
                "email": "test@example.com",
                "company": "Acme Inc",
                "title": title,
                "first_name": "John",
                "last_name": "Doe",
            }

            is_valid, score, issues = monitor.validate_lead(lead_data)

            assert is_valid is False, f"Title '{title}' should be rejected"
            assert any("Generic title" in issue for issue in issues)

    def test_empty_company_rejected(self, monitor: DataQualityMonitor):
        """Test that a lead with empty company is rejected."""
        lead_data = {
            "email": "test@example.com",
            "company": "",
            "title": "VP of Sales",
            "first_name": "John",
            "last_name": "Doe",
        }

        is_valid, score, issues = monitor.validate_lead(lead_data)

        assert is_valid is False
        assert "Company name is empty" in issues

    def test_whitespace_company_rejected(self, monitor: DataQualityMonitor):
        """Test that a lead with whitespace-only company is rejected."""
        lead_data = {
            "email": "test@example.com",
            "company": "   ",
            "title": "VP of Sales",
            "first_name": "John",
            "last_name": "Doe",
        }

        is_valid, score, issues = monitor.validate_lead(lead_data)

        assert is_valid is False
        assert "Company name is empty" in issues

    def test_missing_optional_fields_reduce_score(self, monitor: DataQualityMonitor):
        """Test that missing optional fields reduce the quality score."""
        lead_data = {
            "email": "test@example.com",
            "company": "Acme Inc",
            "title": "VP of Engineering",
            # No first_name, last_name, phone, linkedin
        }

        is_valid, score, issues = monitor.validate_lead(lead_data)

        assert is_valid is True
        assert score < 100.0
        assert score == 65.0  # email(25) + company(20) + title(20)


class TestEnrichmentValidation:
    """Tests for enrichment data validation."""

    def test_enrichment_with_triggers_passes(self, monitor: DataQualityMonitor):
        """Test that enrichment with trigger events passes."""
        enrichment_data = {
            "trigger_events": ["funding_round", "new_hire"],
            "talking_points": [],
            "company_news": [],
        }

        is_valid, score, issues = monitor.validate_enrichment(enrichment_data)

        assert is_valid is True
        assert score >= 40.0

    def test_enrichment_with_talking_points_passes(self, monitor: DataQualityMonitor):
        """Test that enrichment with talking points passes."""
        enrichment_data = {
            "trigger_events": [],
            "talking_points": ["Recent expansion to EU market"],
            "company_news": [],
        }

        is_valid, score, issues = monitor.validate_enrichment(enrichment_data)

        assert is_valid is True
        assert score >= 40.0

    def test_enrichment_without_triggers_fails(self, monitor: DataQualityMonitor):
        """Test that enrichment without triggers or talking points fails."""
        enrichment_data = {
            "trigger_events": [],
            "talking_points": [],
            "company_news": [],
        }

        is_valid, score, issues = monitor.validate_enrichment(enrichment_data)

        assert is_valid is False
        assert "No trigger events found" in issues
        assert "No talking points found" in issues

    def test_enrichment_with_stale_news(self, monitor: DataQualityMonitor):
        """Test that old news (>90 days) is flagged."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        enrichment_data = {
            "trigger_events": ["expansion"],
            "talking_points": ["New market"],
            "company_news": ["Old announcement"],
            "news_date": old_date,
        }

        is_valid, score, issues = monitor.validate_enrichment(enrichment_data)

        assert is_valid is True
        assert "Company news is older than 90 days" in issues

    def test_enrichment_with_fresh_news(self, monitor: DataQualityMonitor):
        """Test that fresh news (<90 days) improves score."""
        fresh_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        enrichment_data = {
            "trigger_events": ["funding"],
            "talking_points": ["Growth story"],
            "company_news": ["New funding round"],
            "news_date": fresh_date,
        }

        is_valid, score, issues = monitor.validate_enrichment(enrichment_data)

        assert is_valid is True
        assert score == 100.0


class TestAutoReject:
    """Tests for auto-rejection logic."""

    def test_auto_reject_below_threshold(self, monitor: DataQualityMonitor):
        """Test that scores below 30 are auto-rejected."""
        assert monitor.should_auto_reject(0.0) is True
        assert monitor.should_auto_reject(10.0) is True
        assert monitor.should_auto_reject(29.9) is True

    def test_no_auto_reject_above_threshold(self, monitor: DataQualityMonitor):
        """Test that scores at or above 30 are not auto-rejected."""
        assert monitor.should_auto_reject(30.0) is False
        assert monitor.should_auto_reject(50.0) is False
        assert monitor.should_auto_reject(100.0) is False


class TestBatchQuality:
    """Tests for batch quality checking."""

    def test_batch_quality_alert(self, monitor: DataQualityMonitor):
        """Test that batch alert is triggered when >50% are rejected."""
        results = [
            {"is_valid": False, "score": 20.0},
            {"is_valid": False, "score": 15.0},
            {"is_valid": False, "score": 10.0},
            {"is_valid": True, "score": 80.0},
        ]

        batch_result = monitor.check_batch_quality(results)

        assert batch_result["alert"] is True
        assert batch_result["rejected"] == 3
        assert batch_result["valid"] == 1
        assert batch_result["rejection_rate"] == 0.75
        assert "High rejection rate" in batch_result["alert_message"]

    def test_batch_quality_no_alert(self, monitor: DataQualityMonitor):
        """Test that no alert is triggered when rejection rate is acceptable."""
        results = [
            {"is_valid": True, "score": 80.0},
            {"is_valid": True, "score": 75.0},
            {"is_valid": True, "score": 90.0},
            {"is_valid": False, "score": 20.0},
        ]

        batch_result = monitor.check_batch_quality(results)

        assert batch_result["alert"] is False
        assert batch_result["rejected"] == 1
        assert batch_result["valid"] == 3

    def test_batch_quality_empty_list(self, monitor: DataQualityMonitor):
        """Test batch quality with an empty results list."""
        batch_result = monitor.check_batch_quality([])

        assert batch_result["total"] == 0
        assert batch_result["alert"] is False
        assert batch_result["rejection_rate"] == 0.0

    def test_source_metrics_tracking(self, monitor: DataQualityMonitor):
        """Test that source metrics are tracked correctly."""
        monitor.record_source_result("apollo", True, 85.0)
        monitor.record_source_result("apollo", True, 90.0)
        monitor.record_source_result("apollo", False, 20.0)

        metrics = monitor.get_source_metrics("apollo")

        assert metrics["total_leads"] == 3
        assert metrics["valid_leads"] == 2
        assert metrics["rejected_leads"] == 1
        assert metrics["average_score"] == pytest.approx(65.0, rel=0.01)
