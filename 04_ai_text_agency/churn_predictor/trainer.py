"""Churn predictor trainer using gradient descent on binary cross-entropy."""

from __future__ import annotations

import math

from churn_predictor.predictor import FEATURE_NAMES, _sigmoid
from logging_config import get_logger

log = get_logger(__name__)


class ChurnTrainer:
    """Trains logistic regression weights via gradient descent."""

    def __init__(
        self,
        learning_rate: float = 0.01,
        epochs: int = 100,
    ) -> None:
        self.learning_rate = learning_rate
        self.epochs = epochs

    def train(self, data: list[dict]) -> dict:
        """Train weights on labeled data.

        Args:
            data: list of dicts with {features: dict, churned: bool}

        Returns:
            dict with {weights: dict, bias: float, final_loss: float}
        """
        if not data:
            return {"weights": {n: 0.0 for n in FEATURE_NAMES}, "bias": 0.0, "final_loss": 0.0}

        # Initialize weights
        weights = {name: 0.0 for name in FEATURE_NAMES}
        bias = 0.0

        n = len(data)

        for epoch in range(self.epochs):
            # Compute gradients
            grad_w = {name: 0.0 for name in FEATURE_NAMES}
            grad_b = 0.0
            total_loss = 0.0

            for sample in data:
                features = sample["features"]
                y = 1.0 if sample["churned"] else 0.0

                # Forward pass
                z = bias
                for name in FEATURE_NAMES:
                    z += weights[name] * features.get(name, 0.0)
                pred = _sigmoid(z)

                # Binary cross-entropy loss
                eps = 1e-15
                pred_clipped = max(eps, min(1 - eps, pred))
                loss = -(y * math.log(pred_clipped) + (1 - y) * math.log(1 - pred_clipped))
                total_loss += loss

                # Gradient: d_loss/d_w = (pred - y) * x
                error = pred - y
                for name in FEATURE_NAMES:
                    grad_w[name] += error * features.get(name, 0.0)
                grad_b += error

            # Update weights
            for name in FEATURE_NAMES:
                weights[name] -= self.learning_rate * (grad_w[name] / n)
            bias -= self.learning_rate * (grad_b / n)

            avg_loss = total_loss / n
            if epoch % 20 == 0:
                log.info("trainer_epoch", epoch=epoch, loss=round(avg_loss, 4))

        final_loss = total_loss / n
        log.info("training_complete", epochs=self.epochs, final_loss=round(final_loss, 4))

        return {
            "weights": weights,
            "bias": bias,
            "final_loss": final_loss,
        }
