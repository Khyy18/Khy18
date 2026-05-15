# Zenith Combo Bot (Funding + Grid + Momentum)

Торговый бот, запускающий три стратегии параллельно с конфигурируемым
распределением капитала:

| Стратегия    | Доля | Описание                                          | Статус      |
|-------------|------|---------------------------------------------------|-------------|
| Funding-arb | 70%  | Delta-neutral арбитраж ставок между биржами       | ОСНОВНАЯ    |
| Grid        | 25%  | Сеточная торговля в диапазоне                     | АКТИВНА     |
| Momentum/MR | 5%   | Regime-adaptive mean-reversion (отключён)         | ОТКЛЮЧЕНА   |

## Ожидаемая доходность (агрессивный режим)

На $550 капитала (50 000₽ при курсе 90₽/$):

| Стратегия | Capital | Leverage | Notional | APR | Месяц |
|-----------|---------|----------|----------|-----|-------|
| Funding-арб | $385 | 5x | $1925 | 20-35% | $8-18 |
| Grid | $137 | 1x | $137 | 20-30% | $3-6 |
| MR | $27 | 5x | $137 | 0% (off) | $0 |
| **ИТОГО** | **$550** | | | **35-50%** | **$11-24** |

Годовая доходность: 35-50% ($192-$330 = 17 000-30 000₽)
Банковский вклад РФ: 18% ($99 = 8 900₽)
**Бот: в 2-3x лучше банка**

Max drawdown: 15% ($82 = 7 500₽) -- kill-switch

---

## Архитектура

| Файл                      | Назначение                                          |
|---------------------------|-----------------------------------------------------|
| `combo_main.py`           | Точка входа: запуск всех стратегий в asyncio        |
| `combo_config.py`         | Конфигурация комбо-бота (аллокация, параметры)      |
| `combo_telegram.py`       | Telegram-интерфейс: статус, команды, kill-switch    |
| `grid_engine.py`          | Grid-стратегия                                      |
| `momentum_engine.py`      | Momentum-стратегия (EMA + ATR + trailing)           |
| `optimize.py`             | Оптимизатор параметров momentum (random + hillclimb)|
| `backtest_momentum.py`    | Бэктест momentum-стратегии на исторических свечах   |
| `capital_allocator.py`    | Динамическое распределение капитала между стратегиями|
| `global_kill_switch.py`   | Глобальный аварийный стоп при превышении drawdown   |
| `exchanges/*.py`          | Адаптеры бирж (Bybit, OKX, Binance, Gate и др.)    |
| `telegram_bot.py`         | Базовый Telegram-бот (funding-only)                 |
| `dashboard.py`            | Web-дашборд (equity, PnL, позиции)                  |
| `config.py`               | Базовая конфигурация (ключи, Telegram, режим)       |

---

## Strategies (Regime-Adaptive)

The bot dynamically selects strategy based on market regime (ADX indicator):

### Mean-Reversion (ADX < 25 - ranging/sideways market)
- Enters on RSI extremes: LONG when RSI < 25, SHORT when RSI > 75
- Exits on RSI reversion to 55 or time stop (20 bars)
- Dynamic stop-loss: max(1.5% fixed, ATR * 1.5)
- Break-even: moves SL to entry after +0.5% profit
- Session filter: trades only 08:00-22:00 UTC (peak liquidity)

### Breakout (ADX >= 50 - strong trend)
- Enters on N-bar high/low breakout with volume confirmation (1.5x avg)
- Trailing stop: activates at +1.5%, trails at 1.0% distance
- Max hold: 96 bars (24 hours on 15m)

### Dead Zone (25 <= ADX < 50)
- No entries - market is transitioning, high false signal risk

---

## 6 Enhancements (MR Strategy)

| # | Enhancement | Description | Default |
|---|-------------|-------------|---------|
| 1 | RSI Momentum Filter | Blocks entries when RSI delta (3 bars) exceeds threshold - protects from breakdowns | threshold=20 |
| 2 | Break-Even Stop | Moves SL to entry price after reaching +0.5% profit | auto |
| 3 | Asymmetric RSI | Oversold=25, Overbought=75 (optimized via backtest, +3.7% vs +1.3% with 78) | 25/75 |
| 4 | Volume Confirmation | Requires elevated volume for entry (capitulation signal) | disabled (0) |
| 5 | BB Width Filter | Only enters when Bollinger Bands are narrow (range-bound) | disabled (0) |
| 6 | Dynamic ATR Stop-Loss | SL = max(fixed 1.5%, ATR(14) * 1.5) - adapts to volatility | auto |

---

## Filters and Protections

| Guard | Description | Default |
|-------|-------------|---------|
| Global Kill-Switch | Stops ALL strategies when total drawdown > threshold | 15% |
| File-Based Kill | `touch /app/data/KILL` stops bot even if Telegram API is down | enabled |
| Per-Strategy Daily Loss | Each strategy has independent daily loss limit | grid 2%, momentum 3% |
| Spread Guard | Blocks orders when spread > threshold (liquidity dried up) | 0.5% |
| Correlation Guard | Max 1 same-direction position in correlated group (BTC+ETH) | 1 |
| Macro Blackout | No entries 30min before / 60min after major macro events | enabled |
| Announcement Monitor | Monitors exchange announcements for delistings/maintenance | every 10 min |
| Session Filter | MR trades only during 08:00-22:00 UTC (peak hours) | enabled |
| Circuit Breaker | Disables strategy after consecutive losses | configurable |

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
