"""Tests for ML lead scorer and model trainer integration."""

import os
import random
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.ml_scorer import InsufficientDataError, MLLeadScorer


@pytest.fixture
def ml_scorer():
    """Create MLLeadScorer without loading a model."""
    scorer = MLLeadScorer(model_path="/tmp/nonexistent_model.joblib")
    return scorer


@pytest.fixture
def synthetic_training_data():
    """Generate 150 fake lead records for training."""
    data = []
    industries = ["technology", "healthcare", "finance", "retail", "manufacturing"]
    titles = ["CEO", "VP of Sales", "Senior Engineer", "Manager", "Intern"]

    for i in range(150):
        # Positive leads tend to have higher engagement
        is_positive = i < 50  # 50 positives, 100 negatives
        features = {
            "company_size_bucket": random.choice(["micro", "small", "medium", "large", "enterprise"]),
            "industry": random.choice(industries),
            "title_seniority_level": random.randint(1, 5) if is_positive else random.randint(1, 3),
            "trigger_event_count": random.randint(2, 5) if is_positive else random.randint(0, 2),
            "tech_stack_overlap_score": random.uniform(0.5, 1.0) if is_positive else random.uniform(0.0, 0.5),
            "email_open_count": random.randint(3, 10) if is_positive else random.randint(0, 3),
            "email_click_count": random.randint(1, 5) if is_positive else random.randint(0, 1),
            "time_to_first_open_hours": random.uniform(0.5, 4.0) if is_positive else random.uniform(10.0, 72.0),
            "linkedin_engagement_score": random.uniform(0.5, 1.0) if is_positive else random.uniform(0.0, 0.3),
            "sequence_step_reached": random.randint(2, 4) if is_positive else random.randint(1, 2),
            "day_of_week_sent": random.randint(0, 4),  # weekdays
            "hour_sent": random.randint(9, 17),
        }
        data.append({
            "features": features,
            "label": 1 if is_positive else 0,
        })

    return data


class TestFeatureEngineering:
    """Tests for feature engineering."""

    def test_engineer_features_produces_correct_dict(self, ml_scorer):
        """Test engineer_features produces correct feature dict."""
        lead_data = {
            "company_size": 250,
            "industry": "technology",
            "title": "VP of Engineering",
            "trigger_events": ["funding_round", "new_hire"],
            "tech_stack_overlap_score": 0.75,
        }
        engagement_data = {
            "email_open_count": 5,
            "email_click_count": 2,
            "time_to_first_open_hours": 2.5,
            "linkedin_engagement_score": 0.6,
            "sequence_step_reached": 3,
            "day_of_week_sent": 2,
            "hour_sent": 14,
        }

        features = ml_scorer.engineer_features(lead_data, engagement_data)

        assert features["company_size_bucket"] == "large"  # 250 is "large"
        assert features["industry"] == "technology"
        assert features["title_seniority_level"] == 4  # VP = level 4
        assert features["trigger_event_count"] == 2
        assert features["tech_stack_overlap_score"] == 0.75
        assert features["email_open_count"] == 5
        assert features["email_click_count"] == 2
        assert features["time_to_first_open_hours"] == 2.5
        assert features["linkedin_engagement_score"] == 0.6
        assert features["sequence_step_reached"] == 3
        assert features["day_of_week_sent"] == 2
        assert features["hour_sent"] == 14

    def test_company_size_bucket_mapping(self, ml_scorer):
        """Test company size to bucket mapping."""
        # micro: 1-10
        features = ml_scorer.engineer_features({"company_size": 5, "title": "Dev"}, {})
        assert features["company_size_bucket"] == "micro"

        # small: 11-50
        features = ml_scorer.engineer_features({"company_size": 30, "title": "Dev"}, {})
        assert features["company_size_bucket"] == "small"

        # medium: 51-200
        features = ml_scorer.engineer_features({"company_size": 100, "title": "Dev"}, {})
        assert features["company_size_bucket"] == "medium"

        # large: 201-1000
        features = ml_scorer.engineer_features({"company_size": 500, "title": "Dev"}, {})
        assert features["company_size_bucket"] == "large"

        # enterprise: 1001+
        features = ml_scorer.engineer_features({"company_size": 5000, "title": "Dev"}, {})
        assert features["company_size_bucket"] == "enterprise"

    def test_title_seniority_levels(self, ml_scorer):
        """Test title seniority level detection."""
        test_cases = [
            ("CEO and Founder", 5),
            ("CTO", 5),
            ("VP of Sales", 4),
            ("Director of Engineering", 4),
            ("Engineering Manager", 3),
            ("Senior Software Engineer", 2),
            ("Intern", 1),
            ("Sales Associate", 1),
        ]
        for title, expected_level in test_cases:
            features = ml_scorer.engineer_features(
                {"company_size": 50, "title": title}, {}
            )
            assert features["title_seniority_level"] == expected_level, (
                f"Title '{title}' expected level {expected_level}, "
                f"got {features['title_seniority_level']}"
            )


class TestColdStart:
    """Tests for cold start behavior."""

    def test_cold_start_raises_insufficient_data_error(self, ml_scorer):
        """Test train with < 100 samples raises InsufficientDataError."""
        small_data = [
            {"features": {"company_size_bucket": "small", "industry": "tech",
                          "title_seniority_level": 3, "trigger_event_count": 1,
                          "tech_stack_overlap_score": 0.5, "email_open_count": 2,
                          "email_click_count": 1, "time_to_first_open_hours": 3.0,
                          "linkedin_engagement_score": 0.4, "sequence_step_reached": 2,
                          "day_of_week_sent": 1, "hour_sent": 10},
             "label": 1}
            for _ in range(50)
        ]

        with pytest.raises(InsufficientDataError, match="at least 100 samples"):
            ml_scorer.train(small_data)

    def test_predict_returns_none_when_model_missing(self):
        """Test predict returns None when model file does not exist."""
        scorer = MLLeadScorer(model_path="/tmp/definitely_not_a_model.joblib")
        features = {
            "company_size_bucket": "medium",
            "industry": "tech",
            "title_seniority_level": 3,
            "trigger_event_count": 2,
            "tech_stack_overlap_score": 0.6,
            "email_open_count": 3,
            "email_click_count": 1,
            "time_to_first_open_hours": 2.0,
            "linkedin_engagement_score": 0.5,
            "sequence_step_reached": 2,
            "day_of_week_sent": 3,
            "hour_sent": 11,
        }
        result = scorer.predict(features)
        assert result is None


class TestTrainPredictCycle:
    """Tests for model training and prediction cycle."""

    def test_train_predict_cycle(self, ml_scorer, synthetic_training_data):
        """Test train/predict cycle with synthetic data."""
        metrics = ml_scorer.train(synthetic_training_data)

        # Verify metrics are returned
        assert "auc" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "n_samples" in metrics
        assert metrics["n_samples"] == 150
        assert 0.0 <= metrics["auc"] <= 1.0
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0

        # Predict on a sample
        features = {
            "company_size_bucket": "large",
            "industry": "technology",
            "title_seniority_level": 4,
            "trigger_event_count": 3,
            "tech_stack_overlap_score": 0.8,
            "email_open_count": 5,
            "email_click_count": 3,
            "time_to_first_open_hours": 1.5,
            "linkedin_engagement_score": 0.7,
            "sequence_step_reached": 3,
            "day_of_week_sent": 2,
            "hour_sent": 10,
        }
        prediction = ml_scorer.predict(features)
        assert prediction is not None
        assert 0.0 <= prediction <= 1.0

    def test_save_and_load_model(self, ml_scorer, synthetic_training_data):
        """Test model save and load."""
        ml_scorer.train(synthetic_training_data)

        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
            model_path = f.name

        try:
            ml_scorer.save_model(model_path)
            assert os.path.exists(model_path)

            # Load into a new scorer
            new_scorer = MLLeadScorer(model_path=model_path)

            # Predictions should match
            features = {
                "company_size_bucket": "medium",
                "industry": "healthcare",
                "title_seniority_level": 3,
                "trigger_event_count": 1,
                "tech_stack_overlap_score": 0.4,
                "email_open_count": 2,
                "email_click_count": 1,
                "time_to_first_open_hours": 5.0,
                "linkedin_engagement_score": 0.3,
                "sequence_step_reached": 2,
                "day_of_week_sent": 4,
                "hour_sent": 15,
            }

            pred1 = ml_scorer.predict(features)
            pred2 = new_scorer.predict(features)
            assert pred1 is not None
            assert pred2 is not None
            assert abs(pred1 - pred2) < 0.001
        finally:
            os.unlink(model_path)


class TestLeadScorerIntegration:
    """Tests for LeadScorer integration with ML scorer."""

    @pytest.mark.asyncio
    async def test_lead_scorer_with_ml_weighted_formula(
        self, session_factory, async_session, synthetic_training_data
    ):
        """Test LeadScorer integrates ML prediction with weighted formula."""
        from tests.conftest import make_lead, make_tenant
        from agents.lead_scorer import LeadScorer

        # Train an ML model
        ml_scorer = MLLeadScorer(model_path="/tmp/test_model_integration.joblib")
        ml_scorer.train(synthetic_training_data)

        # Create test data
        tenant = make_tenant()
        lead = make_lead(
            tenant_id=tenant.id,
            enrichment_data={
                "company_size_match": True,
                "industry_match": True,
                "title_seniority_match": True,
                "tech_stack_match": True,
                "trigger_events": ["funding"],
                "company_size": 500,
                "industry": "technology",
                "tech_stack_overlap_score": 0.8,
            },
        )
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        # Score with ML
        scorer = LeadScorer(session_factory, ml_scorer=ml_scorer)
        score = await scorer.score_lead(lead.id)

        # Score should be a valid number
        assert score is not None
        assert score >= 0

        # Clean up
        try:
            os.unlink("/tmp/test_model_integration.joblib")
        except FileNotFoundError:
            pass

    @pytest.mark.asyncio
    async def test_lead_scorer_without_ml_uses_original_formula(
        self, session_factory, async_session
    ):
        """Test LeadScorer without ML uses the original scoring formula."""
        from tests.conftest import make_lead, make_tenant
        from agents.lead_scorer import LeadScorer

        tenant = make_tenant()
        lead = make_lead(
            tenant_id=tenant.id,
            enrichment_data={
                "company_size_match": True,
                "industry_match": True,
            },
        )
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        # Score without ML (ml_scorer=None)
        scorer = LeadScorer(session_factory, ml_scorer=None)
        score = await scorer.score_lead(lead.id)

        # Should use ICP fit scoring only: 20 + 15 = 35
        assert score == 35.0

    @pytest.mark.asyncio
    async def test_predict_with_ml_returns_none_when_no_model(
        self, session_factory, async_session
    ):
        """Test predict_with_ml returns None when ML scorer has no model."""
        from tests.conftest import make_lead, make_tenant
        from agents.lead_scorer import LeadScorer

        # ML scorer with no model loaded
        ml_scorer = MLLeadScorer(model_path="/tmp/nonexistent.joblib")

        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        scorer = LeadScorer(session_factory, ml_scorer=ml_scorer)
        result = await scorer.predict_with_ml(lead.id)
        assert result is None
