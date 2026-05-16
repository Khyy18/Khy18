"""AlertManager: проверка метрик и отправка алертов в Telegram.

Правила:
  - error_rate > 5%: доля 5xx HTTP-ответов
  - latency_p99 > 2s: 99-й перцентиль HTTP latency
  - queue_backlog > 100: длина очереди задач
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

import aiohttp

import config
from logging_config import get_logger
from monitoring.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL, QUEUE_LENGTH

log = get_logger(__name__)


@dataclass
class AlertRule:
    """Описание одного правила алертинга."""

    name: str
    metric_fn: Callable[[], float]
    threshold: float
    comparison_op: str  # "gt" or "lt"
    message_template: str


def _error_rate() -> float:
    """Вычислить долю 5xx-ответов от общего числа HTTP-запросов."""
    total = 0.0
    errors = 0.0
    for sample in HTTP_REQUESTS_TOTAL.collect()[0].samples:
        val = sample.value
        total += val
        labels = sample.labels
        status = str(labels.get("status", ""))
        if status.startswith("5"):
            errors += val
    if total == 0:
        return 0.0
    return errors / total


def _latency_p99() -> float:
    """Приблизительный p99 из Histogram buckets."""
    metrics = HTTP_REQUEST_DURATION.collect()
    if not metrics:
        return 0.0
    histogram_metric = metrics[0]
    count = 0.0
    buckets: list[tuple[float, float]] = []
    for sample in histogram_metric.samples:
        if sample.name.endswith("_count"):
            count += sample.value
        elif sample.name.endswith("_bucket"):
            le = sample.labels.get("le", "+Inf")
            if le == "+Inf":
                le_val = float("inf")
            else:
                le_val = float(le)
            buckets.append((le_val, sample.value))
    if count == 0:
        return 0.0
    target = count * 0.99
    buckets.sort(key=lambda x: x[0])
    for le_val, cumulative in buckets:
        if cumulative >= target:
            return le_val
    return 0.0


def _queue_backlog() -> float:
    """Текущая длина очереди из Gauge."""
    metrics = QUEUE_LENGTH.collect()
    if not metrics:
        return 0.0
    for sample in metrics[0].samples:
        return float(sample.value)
    return 0.0


DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="error_rate",
        metric_fn=_error_rate,
        threshold=config.ALERT_ERROR_RATE_THRESHOLD,
        comparison_op="gt",
        message_template="Error rate {value:.2%} exceeds threshold {threshold:.2%}",
    ),
    AlertRule(
        name="latency_p99",
        metric_fn=_latency_p99,
        threshold=config.ALERT_LATENCY_P99_THRESHOLD,
        comparison_op="gt",
        message_template="Latency p99 {value:.2f}s exceeds threshold {threshold:.2f}s",
    ),
    AlertRule(
        name="queue_backlog",
        metric_fn=_queue_backlog,
        threshold=config.ALERT_QUEUE_BACKLOG_THRESHOLD,
        comparison_op="gt",
        message_template="Queue backlog {value:.0f} exceeds threshold {threshold:.0f}",
    ),
]


class AlertManager:
    """Менеджер алертов: проверяет правила и шлет уведомления в Telegram."""

    def __init__(self, rules: Optional[list[AlertRule]] = None) -> None:
        self.rules = rules if rules is not None else DEFAULT_RULES

    def check_alerts(self) -> list[str]:
        """Проверить все правила и вернуть список сработавших сообщений."""
        triggered: list[str] = []
        for rule in self.rules:
            try:
                value = rule.metric_fn()
            except Exception as exc:
                log.warning("alert_metric_error", rule=rule.name, error=str(exc))
                continue
            fired = False
            if rule.comparison_op == "gt" and value > rule.threshold:
                fired = True
            elif rule.comparison_op == "lt" and value < rule.threshold:
                fired = True
            if fired:
                msg = rule.message_template.format(
                    value=value, threshold=rule.threshold
                )
                triggered.append(msg)
                log.warning("alert_fired", rule=rule.name, value=value, threshold=rule.threshold)
        return triggered

    async def send_alert(self, session: aiohttp.ClientSession, text: str) -> None:
        """Отправить алерт в Telegram."""
        url = (
            f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}"
            f"/sendMessage"
        )
        payload: dict[str, Any] = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": f"\u26a0\ufe0f <b>Alert</b>\n{text}",
            "parse_mode": "HTML",
        }
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    log.error("alert_send_failed", status=resp.status)
        except Exception as exc:
            log.error("alert_send_error", error=str(exc))

    async def run_loop(self, session: aiohttp.ClientSession) -> None:
        """Фоновый цикл: проверка алертов каждые ALERT_CHECK_INTERVAL_SEC секунд."""
        interval = float(config.ALERT_CHECK_INTERVAL_SEC)
        while True:
            messages = self.check_alerts()
            for msg in messages:
                await self.send_alert(session, msg)
            await asyncio.sleep(interval)
