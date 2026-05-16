"""Pricing Service: точка входа для расчета цены.

get_price() применяет PricingModel для вычисления финальной цены.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import config
from logging_config import get_logger
from pricing.model import PricingModel

log = get_logger(__name__)

_model = PricingModel()


def get_price(
    base_price: float,
    service_type: str,
    client_tg_id: Optional[int] = None,
) -> float:
    """Вычислить финальную цену на основе факторов.

    Args:
        base_price: базовая цена услуги.
        service_type: тип услуги (web, bot, ai, etc.).
        client_tg_id: Telegram ID клиента (для проверки повторного клиента).

    Returns:
        Финальная цена с учетом мультипликатора.
    """
    now = datetime.now(tz=timezone.utc)

    factors = {
        "time_of_day": now.hour,
        "workload": 0,  # TODO: получать из реального источника
        "service_type": service_type,
        "client_history": client_tg_id is not None and client_tg_id > 0,
    }

    multiplier = _model.compute_multiplier(factors)
    base_multiplier = config.PRICING_BASE_MULTIPLIER

    final_price = base_price * multiplier * base_multiplier

    log.info(
        "price_computed",
        base_price=base_price,
        multiplier=multiplier,
        base_multiplier=base_multiplier,
        final_price=round(final_price, 2),
        service_type=service_type,
    )

    return round(final_price, 2)
