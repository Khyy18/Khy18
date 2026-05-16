"""Модуль A/B-тестирования рекламных каналов.

Отслеживание конверсий по UTM/source-тегам, автоматическое
распределение бюджета, тест значимости (chi-squared), дашборд в Telegram.
"""

from ad_testing.engine import ABTestEngine

__all__ = ["ABTestEngine"]
