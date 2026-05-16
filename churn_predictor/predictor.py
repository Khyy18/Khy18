"""Churn predictor using logistic regression."""

from __future__ import annotations

import math
from typing import Optional

from logging_config import get_logger

log = get_logger(__name__)

# Default weights (manually tuned)
# Features: days_since_last_order, order_frequency, avg_check, cancellation_rate, total_orders
DEFAULT_WEIGHTS: dict[str, float] = {
    "days_since_last_order": 0.02,
    "order_frequency": -1.5,
    "avg_check": -0.001,
    "cancellation_rate": 2.0,
    "total_orders": -0.1,
}
DEFAULT_BIAS: float = -1.0

FEATURE_NAMES = [
    "days_since_last_order",
    "order_frequency",
    "avg_check",
    "cancellation_rate",
    "total_orders",
]


def _sigmoid(x: float) -> float:
    """Sigmoid activation function."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        # Numerically stable for negative x
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)


class ChurnPredictor:
    """Predicts churn probability using logistic regression."""

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        bias: Optional[float] = None,
    ) -> None:
        self.weights = weights if weights is not None else DEFAULT_WEIGHTS.copy()
        self.bias = bias if bias is not None else DEFAULT_BIAS

    def predict(self, features: dict[str, float]) -> float:
        """Predict churn probability.

        Args:
            features: dict with keys from FEATURE_NAMES.

        Returns:
            Probability between 0 and 1.
        """
        z = self.bias
        for name in FEATURE_NAMES:
            val = features.get(name, 0.0)
            weight = self.weights.get(name, 0.0)
            z += weight * val

        return _sigmoid(z)

    def compute_features(self, tg_id: int) -> dict[str, float]:
        """Compute features for a client from CRM data.

        Args:
            tg_id: Telegram user ID.

        Returns:
            dict of feature values.
        """
        from crm.models import get_client

        client = get_client(tg_id)
        if not client:
            return {name: 0.0 for name in FEATURE_NAMES}

        # Default features (in real system these would come from order history)
        features: dict[str, float] = {
            "days_since_last_order": 30.0,
            "order_frequency": 0.0,
            "avg_check": 0.0,
            "cancellation_rate": 0.0,
            "total_orders": 0.0,
        }

        # Infer from stage
        stage = client.get("stage", "lead")
        if stage == "churned":
            features["days_since_last_order"] = 90.0
            features["cancellation_rate"] = 0.5
        elif stage == "paid":
            features["days_since_last_order"] = 7.0
            features["order_frequency"] = 2.0
            features["avg_check"] = 5000.0
            features["total_orders"] = 5.0
        elif stage == "trial":
            features["days_since_last_order"] = 14.0
            features["order_frequency"] = 0.5
            features["total_orders"] = 1.0

        return features
