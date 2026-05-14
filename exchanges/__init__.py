"""Реестр биржевых адаптеров.

Использование:
    from exchanges import get_adapter
    adapter = get_adapter('bybit')  # или config.EXCHANGE
"""

from __future__ import annotations

from typing import Any

from .base import ExchangeAdapter


_REGISTRY: dict[str, type[ExchangeAdapter]] = {}


def register(name: str, cls: type[ExchangeAdapter]) -> None:
    """Зарегистрировать класс адаптера под именем."""
    _REGISTRY[name.lower()] = cls


def get_adapter(name: str, **kwargs: Any) -> ExchangeAdapter:
    """Получить экземпляр адаптера по имени.
    Выбрасывает KeyError если адаптер не зарегистрирован."""
    key = name.lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys())) or "(нет)"
        raise KeyError(
            f"Биржа '{name}' не зарегистрирована. Доступные: {available}"
        )
    return _REGISTRY[key](**kwargs)


# Авто-регистрация адаптеров при импорте пакета.
from .binance import BinanceAdapter  # noqa: E402
from .bingx import BingXAdapter  # noqa: E402
from .bitget import BitgetAdapter  # noqa: E402
from .bybit import BybitAdapter  # noqa: E402
from .gate import GateAdapter  # noqa: E402
from .htx import HTXAdapter  # noqa: E402
from .mexc import MEXCAdapter  # noqa: E402
from .okx import OKXAdapter  # noqa: E402

register("binance", BinanceAdapter)
register("bingx", BingXAdapter)
register("bitget", BitgetAdapter)
register("bybit", BybitAdapter)
register("gate", GateAdapter)
register("htx", HTXAdapter)
register("mexc", MEXCAdapter)
register("okx", OKXAdapter)
