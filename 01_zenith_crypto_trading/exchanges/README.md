# Добавление нового адаптера биржи

Этот пакет содержит абстрактный интерфейс `ExchangeAdapter` и конкретные
реализации для каждой поддерживаемой биржи.

## Структура

```
exchanges/
    __init__.py   - реестр и фабрика get_adapter(name)
    base.py       - абстрактный класс ExchangeAdapter
    bybit.py      - Bybit V5 (линейные перпетуалы)
```

## Как добавить новую биржу

1. Создайте файл `exchanges/<name>.py` (например `exchanges/binance.py`).
2. Реализуйте класс, наследующий `ExchangeAdapter` из `exchanges.base`.
3. Зарегистрируйте в `exchanges/__init__.py`:
   ```python
   from .binance import BinanceAdapter
   register("binance", BinanceAdapter)
   ```
4. Установите переменную окружения `EXCHANGE=binance` в `.env`.

## Контракт методов

Все методы асинхронные (кроме `validate_and_round_qty`).
При ошибках сети/парсинга методы НЕ пробрасывают исключения.
Вместо этого возвращают `None`, `[]` или dict с `ok=False`.

| Метод | Возврат | Описание |
|-------|---------|----------|
| `get_server_time` | `Optional[int]` | Время сервера в ms |
| `get_balance` | `Optional[float]` | Баланс по монете |
| `get_klines` | `list[dict]` | Свечи `{ts, open, high, low, close, volume}`, старые первыми |
| `get_instrument_info` | `Optional[dict]` | `{min_qty, qty_step, min_notional, tick_size}` |
| `get_orderbook_top` | `Optional[tuple]` | `(best_bid, best_ask)` |
| `get_positions` | `list[dict]` | Открытые позиции с ненулевым size |
| `get_closed_pnl` | `list[dict]` | Реализованный PnL закрытий |
| `get_execution_history` | `list[dict]` | Исполнения по order_id |
| `place_order_with_fallback` | `Optional[dict]` | PostOnly -> Market IOC; вернуть fill_price/fill_qty |
| `set_trading_stop` | `Optional[dict]` | Обновить SL/TP |
| `cancel_order` | `Optional[dict]` | Отменить ордер |
| `get_open_orders` | `list[dict]` | Активные ордера |
| `panic_sell` | `list[dict]` | Экстренное закрытие всех позиций |
| `validate_and_round_qty` | `float` | Синхронный; 0.0 = невалидно |

## Правила реализации

- Логи на русском: `print(f"[EXCHANGE] Ошибка: {exc}")`.
- Каждый HTTP-вызов оборачивать в try/except.
- aiohttp сессия передаётся как первый аргумент (не создаётся внутри).
- Свечи ВСЕГДА сортированы от старых к новым.
- Не использовать сторонние библиотеки бирж (pybit, ccxt, python-binance).
- Подпись запросов реализовать вручную (HMAC или Ed25519 в зависимости от биржи).
