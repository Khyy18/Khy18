"""ML Lead Scorer - machine learning model for lead scoring with feature engineering."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score

logger = logging.getLogger(__name__)

# Title seniority keywords and levels
_SENIORITY_KEYWORDS: dict[int, list[str]] = {
    5: ["ceo", "cto", "cfo", "coo", "cmo", "chief", "founder", "co-founder", "president"],
    4: ["vp", "vice president", "director", "svp", "evp", "head of"],
    3: ["manager", "lead", "senior manager", "team lead"],
    2: ["senior", "specialist", "analyst", "engineer", "developer", "consultant"],
    1: ["intern", "trainee", "junior", "assistant", "coordinator", "associate"],
}

# Company size buckets
_SIZE_BUCKETS: dict[str, tuple[int, int]] = {
    "micro": (1, 10),
    "small": (11, 50),
    "medium": (51, 200),
    "large": (201, 1000),
    "enterprise": (1001, 999999999),
}


class InsufficientDataError(Exception):
    """Raised when there is not enough training data to build a model."""

    pass


class MLLeadScorer:
    """Machine learning lead scorer using GradientBoosting with feature engineering."""

    def __init__(self, model_path: str = "models/lead_scorer_latest.joblib") -> None:
        self._model_path = model_path
        self._model: GradientBoostingClassifier | None = None
        self._feature_names: list[str] = []
        # Try to load existing model
        self._try_load_model()

    def _try_load_model(self) -> None:
        """Attempt to load a saved model from disk."""
        try:
            self.load_model(self._model_path)
        except (FileNotFoundError, OSError):
            logger.debug("No existing model found at %s", self._model_path)

    def engineer_features(self, lead_data: dict[str, Any], engagement_data: dict[str, Any]) -> dict[str, Any]:
        """Create feature dict from lead and engagement data.

        Args:
            lead_data: Dict with lead information (company_size, industry, title, etc).
            engagement_data: Dict with engagement metrics.

        Returns:
            Dict of engineered features ready for model input.
        """
        # Company size bucket
        company_size = lead_data.get("company_size", 0)
        company_size_bucket = self._get_size_bucket(company_size)

        # Industry
        industry = lead_data.get("industry", "unknown")

        # Title seniority level
        title = lead_data.get("title", "")
        title_seniority_level = self._get_seniority_level(title)

        # Trigger events
        trigger_events = lead_data.get("trigger_events", [])
        trigger_event_count = len(trigger_events) if isinstance(trigger_events, list) else 0

        # Tech stack overlap
        tech_stack_overlap_score = float(lead_data.get("tech_stack_overlap_score", 0.0))

        # Engagement metrics
        email_open_count = int(engagement_data.get("email_open_count", 0))
        email_click_count = int(engagement_data.get("email_click_count", 0))

        # Time to first open
        time_to_first_open_hours = float(engagement_data.get("time_to_first_open_hours", -1))

        # LinkedIn engagement
        linkedin_engagement_score = float(engagement_data.get("linkedin_engagement_score", 0.0))

        # Sequence progress
        sequence_step_reached = int(engagement_data.get("sequence_step_reached", 0))

        # Time-based features
        day_of_week_sent = int(engagement_data.get("day_of_week_sent", 0))
        hour_sent = int(engagement_data.get("hour_sent", 9))

        return {
            "company_size_bucket": company_size_bucket,
            "industry": industry,
            "title_seniority_level": title_seniority_level,
            "trigger_event_count": trigger_event_count,
            "tech_stack_overlap_score": tech_stack_overlap_score,
            "email_open_count": email_open_count,
            "email_click_count": email_click_count,
            "time_to_first_open_hours": time_to_first_open_hours,
            "linkedin_engagement_score": linkedin_engagement_score,
            "sequence_step_reached": sequence_step_reached,
            "day_of_week_sent": day_of_week_sent,
            "hour_sent": hour_sent,
        }

    def train(self, training_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Train GradientBoostingClassifier on feature data.

        Args:
            training_data: List of dicts, each with 'features' (dict) and 'label' (0 or 1).

        Returns:
            Dict with training metrics (auc, precision, recall, n_samples).

        Raises:
            InsufficientDataError: If fewer than 100 samples provided.
        """
        if len(training_data) < 100:
            raise InsufficientDataError(
                f"Need at least 100 samples for training, got {len(training_data)}"
            )

        # Prepare feature matrix
        X, y = self._prepare_training_data(training_data)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Train model
        self._model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        self._model.fit(X_train, y_train)

        # Calculate metrics
        y_pred_proba = self._model.predict_proba(X_test)[:, 1]
        y_pred = self._model.predict(X_test)

        try:
            auc = float(roc_auc_score(y_test, y_pred_proba))
        except ValueError:
            auc = 0.0

        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall = float(recall_score(y_test, y_pred, zero_division=0))

        return {
            "auc": round(auc, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "n_samples": len(training_data),
        }

    def predict(self, features: dict[str, Any]) -> float | None:
        """Return probability 0.0-1.0 that a lead will convert.

        Args:
            features: Dict of engineered features from engineer_features().

        Returns:
            Probability float, or None if model is not loaded.
        """
        if self._model is None:
            return None

        try:
            X = self._features_to_array(features)
            proba = self._model.predict_proba(X)[0, 1]
            return float(proba)
        except Exception as exc:
            logger.error("Prediction failed: %s", exc)
            return None

    def save_model(self, path: str) -> None:
        """Save the trained model to disk using joblib.

        Args:
            path: File path to save the model.
        """
        if self._model is None:
            raise ValueError("No model to save - train first")

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        joblib.dump(
            {"model": self._model, "feature_names": self._feature_names},
            path,
        )
        logger.info("Model saved to %s", path)

    def load_model(self, path: str) -> None:
        """Load a trained model from disk using joblib.

        Args:
            path: File path to load the model from.

        Raises:
            FileNotFoundError: If model file does not exist.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        data = joblib.load(path)
        self._model = data["model"]
        self._feature_names = data.get("feature_names", [])
        logger.info("Model loaded from %s", path)

    @staticmethod
    def _get_size_bucket(company_size: int) -> str:
        """Map company size to bucket category."""
        if company_size <= 10:
            return "micro"
        elif company_size <= 50:
            return "small"
        elif company_size <= 200:
            return "medium"
        elif company_size <= 1000:
            return "large"
        else:
            return "enterprise"

    @staticmethod
    def _get_seniority_level(title: str) -> int:
        """Determine seniority level from job title using keyword matching."""
        title_lower = title.lower()

        # Check longer/more specific keywords first (ordered by specificity)
        # Level 5: C-suite
        c_suite = ["ceo", "cto", "cfo", "coo", "cmo", "chief", "founder", "co-founder", "president"]
        for keyword in c_suite:
            # Use word-boundary-like check to avoid substring false positives
            if _word_match(keyword, title_lower):
                return 5

        # Level 4: VP/Director
        vp_dir = ["vp", "vice president", "director", "svp", "evp", "head of"]
        for keyword in vp_dir:
            if _word_match(keyword, title_lower):
                return 4

        # Level 3: Manager
        manager = ["manager", "lead", "senior manager", "team lead"]
        for keyword in manager:
            if _word_match(keyword, title_lower):
                return 3

        # Level 2: Individual contributor
        ic = ["senior", "specialist", "analyst", "engineer", "developer", "consultant"]
        for keyword in ic:
            if _word_match(keyword, title_lower):
                return 2

        # Level 1: Entry level
        entry = ["intern", "trainee", "junior", "assistant", "coordinator", "associate"]
        for keyword in entry:
            if _word_match(keyword, title_lower):
                return 1

        return 2  # Default to individual contributor

    def _prepare_training_data(self, training_data: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
        """Convert training data dicts into numpy arrays for sklearn.

        Returns:
            Tuple of (X feature matrix, y label array).
        """
        X_list = []
        y_list = []

        for item in training_data:
            features = item["features"]
            label = item["label"]
            X_list.append(self._features_to_array(features)[0])
            y_list.append(int(label))

        self._feature_names = self._get_feature_column_names()
        return np.array(X_list), np.array(y_list)

    def _features_to_array(self, features: dict[str, Any]) -> np.ndarray:
        """Convert a feature dict to a numpy array for model input."""
        # Encode company_size_bucket as ordinal
        size_map = {"micro": 0, "small": 1, "medium": 2, "large": 3, "enterprise": 4}
        size_val = size_map.get(features.get("company_size_bucket", "micro"), 0)

        # Encode industry as hash-based numeric (simple approach)
        industry = features.get("industry", "unknown")
        industry_val = hash(industry) % 100 / 100.0

        feature_array = [
            size_val,
            industry_val,
            features.get("title_seniority_level", 2),
            features.get("trigger_event_count", 0),
            features.get("tech_stack_overlap_score", 0.0),
            features.get("email_open_count", 0),
            features.get("email_click_count", 0),
            features.get("time_to_first_open_hours", -1),
            features.get("linkedin_engagement_score", 0.0),
            features.get("sequence_step_reached", 0),
            features.get("day_of_week_sent", 0),
            features.get("hour_sent", 9),
        ]

        return np.array([feature_array])

    @staticmethod
    def _get_feature_column_names() -> list[str]:
        """Return ordered list of feature column names."""
        return [
            "company_size_bucket_ordinal",
            "industry_encoded",
            "title_seniority_level",
            "trigger_event_count",
            "tech_stack_overlap_score",
            "email_open_count",
            "email_click_count",
            "time_to_first_open_hours",
            "linkedin_engagement_score",
            "sequence_step_reached",
            "day_of_week_sent",
            "hour_sent",
        ]


def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword appears as a whole word (or phrase) in text."""
    pattern = r'\b' + re.escape(keyword) + r'\b'
    return bool(re.search(pattern, text))
