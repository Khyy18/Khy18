"""Модуль автоматизации фриланс-площадок (Kwork, FL.ru)."""

from freelance_automation.base import FreelancePlatform, Order
from freelance_automation.kwork import KworkPlatform
from freelance_automation.flru import FLruPlatform
from freelance_automation.scheduler import FreelanceScheduler

__all__ = [
    "FreelancePlatform",
    "Order",
    "KworkPlatform",
    "FLruPlatform",
    "FreelanceScheduler",
]
