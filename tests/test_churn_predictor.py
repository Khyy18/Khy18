"""Tests for churn_predictor module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from churn_predictor.actions import RetentionActions
from churn_predictor.predictor import FEATURE_NAMES, ChurnPredictor, _sigmoid
from churn_predictor.trainer import ChurnTrainer


class TestChurnPredictor:
    """Tests for ChurnPredictor."""

    def test_predict_returns_value_in_range(self):
        predictor = ChurnPredictor()
        features = {
            "days_since_last_order": 30.0,
            "order_frequency": 1.0,
            "avg_check": 3000.0,
            "cancellation_rate": 0.1,
            "total_orders": 5.0,
        }
        result = predictor.predict(features)
        assert 0.0 <= result <= 1.0

    def test_predict_high_risk_client(self):
        predictor = ChurnPredictor()
        # Client with many days since last order, high cancellation rate
        features = {
            "days_since_last_order": 120.0,
            "order_frequency": 0.0,
            "avg_check": 0.0,
            "cancellation_rate": 0.8,
            "total_orders": 1.0,
        }
        result = predictor.predict(features)
        assert result > 0.5

    def test_predict_low_risk_client(self):
        predictor = ChurnPredictor()
        # Active client with good metrics
        features = {
            "days_since_last_order": 2.0,
            "order_frequency": 4.0,
            "avg_check": 10000.0,
            "cancellation_rate": 0.0,
            "total_orders": 20.0,
        }
        result = predictor.predict(features)
        assert result < 0.5

    def test_predict_with_empty_features(self):
        predictor = ChurnPredictor()
        result = predictor.predict({})
        assert 0.0 <= result <= 1.0

    def test_sigmoid_boundaries(self):
        assert _sigmoid(0.0) == 0.5
        assert _sigmoid(100.0) > 0.99
        assert _sigmoid(-100.0) < 0.01

    def test_compute_features_missing_client(self):
        predictor = ChurnPredictor()
        with patch("crm.models.get_client", return_value=None):
            features = predictor.compute_features(12345)
        assert all(name in features for name in FEATURE_NAMES)
        assert all(v == 0.0 for v in features.values())

    def test_compute_features_paid_client(self):
        predictor = ChurnPredictor()
        mock_client = {"tg_id": 123, "name": "Test", "stage": "paid"}
        with patch("crm.models.get_client", return_value=mock_client):
            features = predictor.compute_features(123)
        assert features["days_since_last_order"] == 7.0
        assert features["order_frequency"] == 2.0

    def test_custom_weights(self):
        weights = {name: 0.0 for name in FEATURE_NAMES}
        predictor = ChurnPredictor(weights=weights, bias=0.0)
        features = {name: 100.0 for name in FEATURE_NAMES}
        # With all weights zero and bias zero, sigmoid(0) = 0.5
        assert predictor.predict(features) == 0.5


class TestChurnTrainer:
    """Tests for ChurnTrainer."""

    def test_train_empty_data(self):
        trainer = ChurnTrainer()
        result = trainer.train([])
        assert "weights" in result
        assert "bias" in result
        assert result["final_loss"] == 0.0

    def test_train_improves_loss(self):
        trainer = ChurnTrainer(learning_rate=0.01, epochs=200)

        # Simple dataset with normalized features
        data = [
            {"features": {"days_since_last_order": 0.9, "order_frequency": 0.0, "avg_check": 0.0, "cancellation_rate": 0.5, "total_orders": 0.1}, "churned": True},
            {"features": {"days_since_last_order": 0.6, "order_frequency": 0.1, "avg_check": 0.1, "cancellation_rate": 0.3, "total_orders": 0.2}, "churned": True},
            {"features": {"days_since_last_order": 0.05, "order_frequency": 0.6, "avg_check": 0.5, "cancellation_rate": 0.0, "total_orders": 0.5}, "churned": False},
            {"features": {"days_since_last_order": 0.02, "order_frequency": 0.9, "avg_check": 0.8, "cancellation_rate": 0.0, "total_orders": 0.9}, "churned": False},
        ]

        result = trainer.train(data)
        # Loss should be less than random (log(2) ~ 0.693)
        assert result["final_loss"] < 0.693

    def test_train_returns_weights(self):
        trainer = ChurnTrainer(epochs=10)
        data = [
            {"features": {name: 1.0 for name in FEATURE_NAMES}, "churned": True},
            {"features": {name: 0.0 for name in FEATURE_NAMES}, "churned": False},
        ]
        result = trainer.train(data)
        assert "weights" in result
        assert "bias" in result
        for name in FEATURE_NAMES:
            assert name in result["weights"]


class TestRetentionActions:
    """Tests for RetentionActions."""

    @pytest.mark.asyncio
    async def test_high_risk_sends_discount(self):
        actions = RetentionActions()
        session = AsyncMock()
        resp_mock = AsyncMock()
        resp_mock.status = 200
        resp_mock.json = AsyncMock(return_value={"ok": True})
        resp_mock.__aenter__ = AsyncMock(return_value=resp_mock)
        resp_mock.__aexit__ = AsyncMock(return_value=False)
        session.post.return_value = resp_mock

        await actions.take_action(session, tg_id=12345, churn_risk=0.75)
        # Should have called Telegram API (sendMessage)
        assert session.post.called

    @pytest.mark.asyncio
    async def test_critical_risk_alerts_admin(self):
        actions = RetentionActions()
        session = AsyncMock()
        resp_mock = AsyncMock()
        resp_mock.status = 200
        resp_mock.json = AsyncMock(return_value={"ok": True})
        resp_mock.__aenter__ = AsyncMock(return_value=resp_mock)
        resp_mock.__aexit__ = AsyncMock(return_value=False)
        session.post.return_value = resp_mock

        with patch("churn_predictor.actions.config") as mock_config:
            mock_config.TELEGRAM_CHAT_ID = 99999
            mock_config.TELEGRAM_API_URL = "https://api.telegram.org"
            mock_config.TELEGRAM_TOKEN = "test-token"
            await actions.take_action(session, tg_id=12345, churn_risk=0.95)

        # Should call twice: discount + admin alert
        assert session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_low_risk_no_action(self):
        actions = RetentionActions()
        session = AsyncMock()

        await actions.take_action(session, tg_id=12345, churn_risk=0.3)
        # Should not call anything
        assert not session.post.called
