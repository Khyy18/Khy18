"""Модуль динамического ценообразования AI-агентства."""

from services import SERVICES
from models import ServiceType


def _length_multiplier(text_length: int) -> float:
    """
    Коэффициент за длину текста.

    <=1000 символов -> x1
    <=3000 символов -> x1.5
    <=5000 символов -> x2
    >5000 символов -> x3
    """
    if text_length <= 1000:
        return 1.0
    elif text_length <= 3000:
        return 1.5
    elif text_length <= 5000:
        return 2.0
    else:
        return 3.0


def _urgency_multiplier(urgent: bool) -> float:
    """
    Коэффициент срочности.

    normal -> x1
    urgent -> x1.5
    """
    return 1.5 if urgent else 1.0


def calculate_price(service_type: str, text_length: int, urgent: bool = False) -> float:
    """
    Рассчитать динамическую цену заказа.

    Args:
        service_type: тип услуги (значение ServiceType enum)
        text_length: длина текста в символах
        urgent: срочный заказ или нет

    Returns:
        Итоговая цена в рублях
    """
    try:
        stype = ServiceType(service_type)
    except ValueError:
        return 0.0

    base_price = SERVICES[stype].price
    length_mult = _length_multiplier(text_length)
    urgency_mult = _urgency_multiplier(urgent)

    return base_price * length_mult * urgency_mult
