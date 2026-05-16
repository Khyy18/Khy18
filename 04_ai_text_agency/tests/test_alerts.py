"""Tests for monitoring/alerts.py AlertManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from monitoring.alerts import AlertManager, AlertRule


def _make_rule(value: float, threshold: float, op: str = "gt") -> AlertRule:
    return AlertRule(
        name="test_rule",
        metric_fn=lambda v=value: v,
        threshold=threshold,
        comparison_op=op,
        message_template="Value {value:.2f} crossed {threshold:.2f}",
    )


class TestAlertRuleEvaluation:
    def test_gt_fires_when_above_threshold(self) -> None:
        rule = _make_rule(0.10, 0.05, "gt")
        mgr = AlertManager(rules=[rule])
        alerts = mgr.check_alerts()
        assert len(alerts) == 1
        assert "0.10" in alerts[0]

    def test_gt_silent_when_below_threshold(self) -> None:
        rule = _make_rule(0.03, 0.05, "gt")
        mgr = AlertManager(rules=[rule])
        alerts = mgr.check_alerts()
        assert len(alerts) == 0

    def test_gt_silent_when_equal_threshold(self) -> None:
        rule = _make_rule(0.05, 0.05, "gt")
        mgr = AlertManager(rules=[rule])
        alerts = mgr.check_alerts()
        assert len(alerts) == 0

    def test_lt_fires_when_below_threshold(self) -> None:
        rule = _make_rule(1.0, 2.0, "lt")
        mgr = AlertManager(rules=[rule])
        alerts = mgr.check_alerts()
        assert len(alerts) == 1

    def test_multiple_rules_all_fire(self) -> None:
        rules = [
            _make_rule(0.10, 0.05, "gt"),
            _make_rule(3.0, 2.0, "gt"),
        ]
        mgr = AlertManager(rules=rules)
        alerts = mgr.check_alerts()
        assert len(alerts) == 2

    def test_metric_fn_exception_handled(self) -> None:
        def bad_fn() -> float:
            raise RuntimeError("oops")

        rule = AlertRule(
            name="bad",
            metric_fn=bad_fn,
            threshold=1.0,
            comparison_op="gt",
            message_template="{value}",
        )
        mgr = AlertManager(rules=[rule])
        alerts = mgr.check_alerts()
        assert len(alerts) == 0


class TestAlertManagerSend:
    @pytest.mark.asyncio
    async def test_send_alert_calls_telegram(self) -> None:
        mgr = AlertManager(rules=[])
        session = AsyncMock()
        resp_mock = AsyncMock()
        resp_mock.status = 200
        session.post.return_value.__aenter__ = AsyncMock(return_value=resp_mock)
        session.post.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("monitoring.alerts.config") as mock_config:
            mock_config.TELEGRAM_API_URL = "https://api.telegram.org"
            mock_config.TELEGRAM_TOKEN = "test_token"
            mock_config.TELEGRAM_CHAT_ID = 12345
            await mgr.send_alert(session, "test alert")

        session.post.assert_called_once()
        call_kwargs = session.post.call_args
        assert "test_token" in call_kwargs[0][0] or "test_token" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_check_alerts_triggers_send_on_breach(self) -> None:
        rule = _make_rule(0.10, 0.05, "gt")
        mgr = AlertManager(rules=[rule])
        mgr.send_alert = AsyncMock()

        session = AsyncMock()
        # Simulate one loop iteration manually
        messages = mgr.check_alerts()
        for msg in messages:
            await mgr.send_alert(session, msg)

        mgr.send_alert.assert_called_once()
        call_text = mgr.send_alert.call_args[0][1]
        assert "0.10" in call_text

    @pytest.mark.asyncio
    async def test_no_alert_when_below_threshold(self) -> None:
        rule = _make_rule(0.01, 0.05, "gt")
        mgr = AlertManager(rules=[rule])
        mgr.send_alert = AsyncMock()

        messages = mgr.check_alerts()
        for msg in messages:
            await mgr.send_alert(AsyncMock(), msg)

        mgr.send_alert.assert_not_called()
