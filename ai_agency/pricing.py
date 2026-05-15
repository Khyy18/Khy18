"""Модуль динамического ценообразования AI-агентства."""

from services import SERVICES
from models import ServiceType

# Интеграция demand_pricing (graceful)
try:
    import demand_pricing as _demand_pricing
except ImportError:
    _demand_pricing = None

# Интеграция loyalty (graceful)
try:
    import loyalty as _loyalty
except ImportError:
    _loyalty = None


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


def calculate_price(service_type: str, text_length: int, urgent: bool = False, telegram_id: int = None) -> float:
    """
    Рассчитать динамическую цену заказа.

    Args:
        service_type: тип услуги (значение ServiceType enum)
        text_length: длина текста в символах
        urgent: срочный заказ или нет
        telegram_id: ID клиента для расчёта скидки лояльности (опционально)

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
