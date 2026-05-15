"""Адаптеры платформ для мультиплатформенной поддержки AI-агентства."""

from .telegram import TelegramAdapter
from .whatsapp import WhatsAppAdapter
from .vk import VKAdapter

__all__ = ["TelegramAdapter", "WhatsAppAdapter", "VKAdapter"]
