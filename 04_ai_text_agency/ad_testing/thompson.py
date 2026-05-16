"""Thompson Sampling для A/B-тестирования рекламных каналов.

Использует Beta-распределение (scipy.stats.beta) для байесовского
подхода к multi-armed bandit задаче оптимизации бюджета.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import beta as beta_dist

from logging_config import get_logger

log = get_logger(__name__)


class ThompsonSamplingEngine:
    """Движок Thompson Sampling на основе Beta-распределения."""

    def sample_arm(self, alpha: float, beta: float) -> float:
        """Сэмплировать значение из Beta(alpha, beta).

        Args:
            alpha: Параметр alpha (успехи + 1).
            beta: Параметр beta (неудачи + 1).

        Returns:
            Случайное значение из Beta-распределения в [0, 1].
        """
        return float(beta_dist.rvs(alpha, beta))

    def select_best_arm(self, channels: list[dict]) -> str:
        """Выбрать лучший канал по результатам сэмплирования.

        Args:
            channels: Список словарей с ключами source_tag, alpha_param, beta_param.

        Returns:
            source_tag канала с наивысшим сэмплом.
        """
        if not channels:
            return ""

        best_tag = ""
        best_sample = -1.0

        for ch in channels:
            alpha = ch.get("alpha_param", 1.0)
            beta = ch.get("beta_param", 1.0)
            sample = self.sample_arm(alpha, beta)
            if sample > best_sample:
                best_sample = sample
                best_tag = ch["source_tag"]

        return best_tag

    def update_arm(
        self, source_tag: str, is_conversion: bool, channels: list[dict]
    ) -> tuple[float, float]:
        """Обновить параметры Beta-распределения для канала.

        Args:
            source_tag: Идентификатор канала.
            is_conversion: True если конверсия (успех), False если нет.
            channels: Список каналов для поиска текущих параметров.

        Returns:
            Обновленные (alpha, beta) параметры.
        """
        alpha = 1.0
        beta = 1.0

        for ch in channels:
            if ch["source_tag"] == source_tag:
                alpha = ch.get("alpha_param", 1.0)
                beta = ch.get("beta_param", 1.0)
                break

        if is_conversion:
            alpha += 1.0
        else:
            beta += 1.0

        log.debug(
            "thompson_arm_updated",
            source_tag=source_tag,
            is_conversion=is_conversion,
            alpha=alpha,
            beta=beta,
        )
        return alpha, beta

    def allocate_budget_thompson(
        self, total_budget: float, channels: list[dict]
    ) -> dict[str, float]:
        """Распределить бюджет пропорционально сэмплам Thompson Sampling.

        Args:
            total_budget: Общий бюджет для распределения.
            channels: Список каналов с alpha_param и beta_param.

        Returns:
            Словарь {source_tag: allocated_budget}.
        """
        if not channels:
            return {}

        if len(channels) == 1:
            return {channels[0]["source_tag"]: total_budget}

        # Сэмплируем из Beta для каждого канала
        samples: dict[str, float] = {}
        for ch in channels:
            alpha = ch.get("alpha_param", 1.0)
            beta = ch.get("beta_param", 1.0)
            samples[ch["source_tag"]] = self.sample_arm(alpha, beta)

        # Нормализуем сэмплы для пропорционального распределения
        total_samples = sum(samples.values())
        if total_samples <= 0:
            # Равномерное распределение при нулевых сэмплах
            per_channel = total_budget / len(channels)
            return {ch["source_tag"]: per_channel for ch in channels}

        allocation: dict[str, float] = {}
        for tag, sample in samples.items():
            allocation[tag] = (sample / total_samples) * total_budget

        return allocation
