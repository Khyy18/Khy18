# Zenith Combo Bot (Funding + Grid)

Торговый бот, запускающий две стратегии параллельно с конфигурируемым
распределением капитала:

| Стратегия    | Доля | Описание                                          | Статус      |
|-------------|------|---------------------------------------------------|-------------|
| Funding-arb | 75%  | Delta-neutral арбитраж ставок между биржами       | ОСНОВНАЯ    |
| Grid        | 25%  | Сеточная торговля в диапазоне                     | АКТИВНА     |

## Ожидаемая доходность (агрессивный режим)

На $550 капитала (50 000 руб. при курсе 90 руб./$):

| Стратегия | Capital | Leverage | Notional | APR | Месяц |
|-----------|---------|----------|----------|-----|-------|
| Funding-арб | $412 | 5x | $2062 | 20-35% | $9-20 |
| Grid | $137 | 1x | $137 | 20-30% | $3-6 |
| **ИТОГО** | **$550** | | | **35-50%** | **$12-26** |

Годовая доходность: 35-50% ($192-$330 = 17 000-30 000 руб.)
Банковский вклад РФ: 18% ($99 = 8 900 руб.)
**Бот: в 2-3x лучше банка**

Max drawdown: 15% ($82 = 7 500 руб.) -- kill-switch

---

## Архитектура

| Файл                      | Назначение                                          |
|---------------------------|-----------------------------------------------------|
| `combo_main.py`           | Точка входа: запуск всех стратегий в asyncio        |
| `combo_config.py`         | Конфигурация комбо-бота (аллокация, параметры)      |
| `combo_telegram.py`       | Telegram-интерфейс: статус, команды, kill-switch    |
| `grid_engine.py`          | Grid-стратегия                                      |
| `capital_allocator.py`    | Динамическое распределение капитала между стратегиями|
| `global_kill_switch.py`   | Глобальный аварийный стоп при превышении drawdown   |
| `exchanges/*.py`          | Адаптеры бирж (Bybit, OKX, Binance, Gate и др.)    |
| `telegram_bot.py`         | Базовый Telegram-бот (funding-only)                 |
| `dashboard.py`            | Web-дашборд (equity, PnL, позиции)                  |
| `config.py`               | Базовая конфигурация (ключи, Telegram, режим)       |

---

## Filters and Protections

| Guard | Description | Default |
|-------|-------------|---------|
| Global Kill-Switch | Stops ALL strategies when total drawdown > threshold | 15% |
| File-Based Kill | `touch /app/data/KILL` stops bot even if Telegram API is down | enabled |
| Per-Strategy Daily Loss | Each strategy has independent daily loss limit | grid 2% |
| Spread Guard | Blocks orders when spread > threshold (liquidity dried up) | 0.5% |
| Macro Blackout | No entries 30min before / 60min after major macro events | enabled |
| Announcement Monitor | Monitors exchange announcements for delistings/maintenance | every 10 min |

---

## AI-модули

| Файл                   | Назначение                                      |
|------------------------|-------------------------------------------------|
| `ai_integration.py`   | Интеграция с LLM для анализа рынка              |
| `regime_classifier.py`| Классификация рыночного режима (тренд/флэт)     |
| `ml_curator.py`       | ML-курирование символов для стратегий            |
| `signal_scorer.py`    | Скоринг торговых сигналов                        |
| `anomaly_detector.py` | Детектор аномалий (объем, спред, волатильность)  |

---

## Запуск

```bash
python combo_main.py
```

### Docker

```bash
docker compose -f deploy/docker-compose.yml up
```

---

## Переменные окружения

Скопируйте `deploy/.env.example` (или `.env.example` в корне) в `.env` и заполните:

```bash
cp .env.example .env
```

Основные параметры: Telegram-токен, ключи бирж, капитал, аллокация стратегий.
Полный список параметров смотрите в файле `.env.example`.

---

## Тесты

```bash
python -m pytest tests/ -v
```
