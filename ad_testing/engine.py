"""Движок A/B-тестирования рекламных каналов.

ABTestEngine - основной класс для управления каналами,
записи событий, распределения бюджета и расчета значимости.
"""

from __future__ import annotations

from ad_testing import models
from ad_testing.stats import chi_squared_test
from ad_testing.thompson import ThompsonSamplingEngine
from logging_config import get_logger

log = get_logger(__name__)


class ABTestEngine:
    """Движок A/B-тестирования рекламных каналов."""

    def __init__(self) -> None:
        models.init_db()

    def register_channel(self, name: str, source_tag: str) -> int:
        """Зарегистрировать рекламный канал. Возвращает id."""
        channel_id = models.register_channel(name, source_tag)
        log.info("channel_registered", name=name, source_tag=source_tag, channel_id=channel_id)
        return channel_id

    def record_event(
        self, source_tag: str, event_type: str, revenue: float = 0.0
    ) -> None:
        """Записать событие: click, conversion, impression."""
        models.record_event(source_tag, event_type, revenue)
        log.debug("event_recorded", source_tag=source_tag, event_type=event_type, revenue=revenue)

    def allocate_budget(self, total_budget: float) -> dict[str, float]:
        """Распределить бюджет: 80% лучшим (по конверсии), 20% экспериментальным.

        Лучшие - каналы с наибольшей конверсионной ставкой (clicks > 0).
        Экспериментальные - каналы с наименьшим количеством данных.
        """
        channels = models.list_channels()
        if not channels:
            return {}

        # Вычислить конверсионную ставку для каждого канала
        for ch in channels:
            clicks = ch.get("clicks", 0)
            conversions = ch.get("conversions", 0)
            ch["conversion_rate"] = conversions / clicks if clicks > 0 else 0.0

        # Сортировка: лучшие по конверсии сверху
        sorted_channels = sorted(
            channels, key=lambda c: c["conversion_rate"], reverse=True
        )

        # Если только 1 канал - весь бюджет ему
        if len(sorted_channels) == 1:
            return {sorted_channels[0]["source_tag"]: total_budget}

        # Разделить на топ-перформеров и экспериментальные
        # Топ-перформеры: верхняя половина (минимум 1)
        split_idx = max(1, len(sorted_channels) // 2)
        top_channels = sorted_channels[:split_idx]
        experimental_channels = sorted_channels[split_idx:]

        # Если нет экспериментальных - все деньги топам
        if not experimental_channels:
            budget_per_top = total_budget / len(top_channels)
            return {ch["source_tag"]: budget_per_top for ch in top_channels}

        # 80% топам, 20% экспериментальным
        top_budget = total_budget * 0.8
        exp_budget = total_budget * 0.2

        allocation: dict[str, float] = {}

        budget_per_top = top_budget / len(top_channels)
        for ch in top_channels:
            allocation[ch["source_tag"]] = budget_per_top

        budget_per_exp = exp_budget / len(experimental_channels)
        for ch in experimental_channels:
            allocation[ch["source_tag"]] = budget_per_exp

        return allocation

    def compute_significance(self, tag_a: str, tag_b: str) -> dict:
        """Рассчитать статистическую значимость различий между каналами.

        Возвращает словарь с chi2, p_value, is_significant, winner,
        conversion_rate_a, conversion_rate_b.
        """
        ch_a = models.get_channel_stats(tag_a)
        ch_b = models.get_channel_stats(tag_b)

        if not ch_a or not ch_b:
            return {
                "chi2": 0.0,
                "p_value": 1.0,
                "is_significant": False,
                "winner": None,
                "conversion_rate_a": 0.0,
                "conversion_rate_b": 0.0,
            }

        clicks_a = ch_a.get("clicks", 0)
        clicks_b = ch_b.get("clicks", 0)
        conv_a = ch_a.get("conversions", 0)
        conv_b = ch_b.get("conversions", 0)

        rate_a = conv_a / clicks_a if clicks_a > 0 else 0.0
        rate_b = conv_b / clicks_b if clicks_b > 0 else 0.0

        chi2, p_value = chi_squared_test(conv_a, clicks_a, conv_b, clicks_b)

        is_significant = p_value < 0.05
        winner = None
        if is_significant:
            winner = tag_a if rate_a > rate_b else tag_b

        return {
            "chi2": chi2,
            "p_value": p_value,
            "is_significant": is_significant,
            "winner": winner,
            "conversion_rate_a": rate_a,
            "conversion_rate_b": rate_b,
        }

    def get_dashboard_data(self) -> dict:
        """Сводка по всем каналам для дашборда."""
        channels = models.list_channels()
        summary = []
        for ch in channels:
            clicks = ch.get("clicks", 0)
            conversions = ch.get("conversions", 0)
            impressions = ch.get("impressions", 0)
            ctr = clicks / impressions if impressions > 0 else 0.0
            conv_rate = conversions / clicks if clicks > 0 else 0.0
            summary.append({
                "name": ch["name"],
                "source_tag": ch["source_tag"],
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "spend": ch.get("spend", 0.0),
                "revenue": ch.get("revenue", 0.0),
                "ctr": ctr,
                "conversion_rate": conv_rate,
            })
        return {
            "channels": summary,
            "total_channels": len(summary),
        }

    def allocate_budget_thompson(self, total_budget: float) -> dict[str, float]:
        """Распределить бюджет через Thompson Sampling.

        Использует Beta-распределение для байесовского подхода
        к multi-armed bandit задаче. Более эффективен, чем
        фиксированное 80/20 разделение из allocate_budget().
        """
        channels = models.list_channels()
        if not channels:
            return {}

        ts_engine = ThompsonSamplingEngine()
        allocation = ts_engine.allocate_budget_thompson(total_budget, channels)
        log.info(
            "budget_allocated_thompson",
            total_budget=total_budget,
            allocation=allocation,
        )
        return allocation

    def record_event_thompson(
        self, source_tag: str, event_type: str, revenue: float = 0.0
    ) -> None:
        """Записать событие и обновить параметры Thompson Sampling.

        Помимо обычной записи события, обновляет alpha/beta параметры
        Beta-распределения для данного канала.
        """
        # Записать событие как обычно
        models.record_event(source_tag, event_type, revenue)

        # Обновить Beta-параметры для Thompson Sampling
        if event_type in ("click", "conversion"):
            is_conversion = event_type == "conversion"
            # Direct O(1) lookup instead of loading all channels
            alpha, beta = models.get_beta_params(source_tag)
            if is_conversion:
                alpha += 1.0
            else:
                beta += 1.0
            models.update_beta_params(source_tag, alpha, beta)
            log.debug(
                "thompson_params_updated",
                source_tag=source_tag,
                event_type=event_type,
                alpha=alpha,
                beta=beta,
            )
