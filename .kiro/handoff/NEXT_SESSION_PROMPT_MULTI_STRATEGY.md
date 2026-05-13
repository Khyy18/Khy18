# Next session: переход на Multi-Strategy Ensemble + Meta-Learning

## Контекст для нового сессионного агента

Это handoff из сессии 2026-05-13. Прочти его и steering-файл `Khy18/.kiro/steering/zenith-control-v3.md` ПЕРЕД любыми действиями.

## ВАЖНО: Финальный выбор архитектуры

После 8 итераций обсуждения с пользователем выбран **Multi-Strategy Ensemble с мета-обучаемым ИИ-фильтром**. Это **финальное решение**, не предлагать альтернативы.

Раньше планировался DL ensemble (LSTM + LightGBM + PPO) — его handoff в файле `NEXT_SESSION_PROMPT_DL.md` устарел и должен **игнорироваться**. Использовать ТОЛЬКО этот файл (`NEXT_SESSION_PROMPT_MULTI_STRATEGY.md`).

## Ключевая фраза пользователя (verbatim)

> "В общем, напиши промт для перехода на новую сессию, где ты создашь и подготовишь все для этой стратегии, адапнируешь все под телеграмм бота управления торговлей в таком же духе, но для этой стратегии, дашь список что нужно добавить для работы этой стратегии, имею в виду API и все такое, все что тебе нужно я предоставлю не ограничивай себя и свои возможности, не ориентируйся на то что у меня есть, если будет нужно что я добавлю ты только скажи что"

**Ключевая директива:** пользователь готов предоставить любые API, дополнительные сервисы, ресурсы. Не ограничиваться текущим окружением. Если нужен платный сервис ради качества — сказать пользователю что нужно подключить.

## Параметры запуска

- **Биржа:** OKX (тот же API).
- **Счёт:** ДЕМО (`IS_TESTNET=true` в `.env`). Реальные деньги не задействованы.
- **Стартовый капитал:** $5,000 виртуальных USDT на демо.
- **Универсум:** 7 пар из `config.SYMBOLS` (BTC/ETH/SOL/BNB/XRP/DOGE/AVAX-USDT-SWAP).
- **Goal:** не скальпинг, hold time 30 минут - 4 часа, 5-15 сделок в день, ансамбль из 5 стратегий с meta-learning координатором, expected ~22% годовых при MaxDD ~15%.

## Архитектура Multi-Strategy Ensemble

### High-level схема

```
[OKX Market Data] (websocket + REST, 7 пар)
        ↓
[Feature pipeline] (классическая система — 50+ features)
        ↓
   ┌────┬─────────┬─────────┬───────────┬──────────┐
   ▼    ▼         ▼         ▼           ▼          ▼
[Trend][Mean    [Vol      [Cross-asset][Funding   ← 5 sub-стратегий
 Follow Revert] Breakout]  Momentum]   Arbitrage]    (детерминированные правила)
   │    │         │         │           │
   └────┴────┬────┴─────────┴───────────┘
             ▼
   ┌──────────────────────────┐
   │  Meta-Learner (LightGBM) │   ← главный ИИ
   │  Решает веса 5 стратегий │      на основе текущего регима
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Anomaly Detector        │   ← вспомогательный ИИ
   │  (IsolationForest)       │      ловит аномалии рынка
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Decision Aggregator     │   ← классическая система
   │  (взвешивает сигналы)    │
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  AI-Gate (Groq LLM)      │   ← существующий слой, оставляем
   │  veto на red-flag news   │
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Risk Manager (система)  │   ← существующий слой, оставляем
   │  GLOBAL_RISK_CAP, kill   │
   └──────────────────────────┘
             ↓ APPROVED
   ┌──────────────────────────┐
   │  Order Engine (OKX)      │
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Telegram Bot (UI 80%)   │
   └──────────────────────────┘
```

### 5 sub-стратегий (детерминированные, без ML)

| # | Стратегия | Файл | Откуда брать | Сложность |
|---|-----------|------|--------------|-----------|
| 1 | **Trend Following** (Donchian + EMA + ATR) | `Khy18/strategy_v2.py` (существующий) | **Уже есть**, нужно только зафиксить look-ahead bias | 1/5 |
| 2 | **Mean Reversion** (Bollinger + RSI + Z-score) | `Khy18/strategy_v2_meanrevert.py` (скелет 391 строк) | **Уже есть скелет**, доделать и валидировать | 2/5 |
| 3 | **Volatility Breakout** (Keltner Channels + ATR expansion) | `Khy18/strategies/vol_breakout.py` (новый) | Писать с нуля, ~250 строк | 2/5 |
| 4 | **Cross-asset Momentum** (ranking 7 пар по 7d return) | `Khy18/strategies/xasset_momentum.py` (новый) | Писать с нуля, ~200 строк | 2/5 |
| 5 | **Funding Arbitrage** (delta-neutral на positive funding) | `Khy18/strategies/funding_arb.py` (новый) | Писать с нуля + downloader funding history, ~500 строк | 3/5 |

**Все 5 sub-стратегий — это правила**, не ML. Они детерминированные, прозрачные, легко тестируются юнит-тестами.

### ИИ-компоненты (всего 8 ИИ)

#### Группа A: Локальные ML-модели (ядро ансамбля)

| ИИ | Роль | Источник | Стоимость |
|----|------|----------|-----------|
| **LightGBM Meta-Learner** | Главный ИИ. Решает веса 5 sub-стратегий на основе текущего регима | `pip install lightgbm` | $0 |
| **IsolationForest Anomaly Detector** | Ловит аномальное поведение рынка (защита от чёрных лебедей) | `pip install scikit-learn` | $0 |

**Тренируются и работают на CPU.** Никакого GPU. Никаких API. Просто Python.

#### Группа B: Через Groq (один существующий ключ → 5+ моделей)

Через `GROQ_API_KEY` доступ к разным моделям. **Один ключ — много моделей.**

| Slot | Модель Groq | Задача | Текущий код |
|------|-------------|--------|-------------|
| AI-Gate | `llama-3.1-8b-instant` | Veto перед сделкой по red-flag в новостях | `ai_trade_gate.py` (есть) |
| Macro-sentinel | `llama-3.1-8b-instant` | FOMC/CPI blackout | `ai_macro_sentinel.py` (есть) |
| Regime classifier | `llama-3.1-8b-instant` | TRENDING/RANGING/CRISIS → подаёт фичи в Meta-Learner | `ai_regime.py` (есть, расширить) |
| AI-Analyst | `llama-3.3-70b-versatile` | Telegram-чат с пояснениями | `ai_analyst.py` (есть) |
| Postmortem | `llama-3.3-70b-versatile` | Еженедельный отчёт | `ai_postmortem.py` (есть) |
| **ML Explainer** (новый) | `qwen-2.5-72b-instruct` | Объясняет в Telegram, почему Meta-Learner выбрал эту стратегию | новый код в `ai_analyst.py` |

#### Группа C: Опциональные внешние ИИ (если пользователь готов добавить)

Эти **не нужны** для базовой версии. Но могут улучшить систему:

| ИИ | Сервис | Free tier | Регистрация | Зачем нужен |
|----|--------|-----------|-------------|-------------|
| **Backup classifier** | Hugging Face Inference API | 1000 req/день | https://huggingface.co/join (2 мин) | Backup если Groq упал — fallback на HF |
| **Reasoning model** | DeepSeek-R1 через Groq (есть в free tier) | См. Groq лимиты | Уже есть ключ | Глубокий разбор проигрышных сделок |
| **Sentiment analysis** | Cloudflare Workers AI | 10k req/день | https://dash.cloudflare.com (2 мин) | Дополнительный sentiment-слой |
| **Локальная reasoning model** | Ollama (Llama 3 / Qwen 2.5) | $0, работает на сервере | https://ollama.com (5 мин установка) | Полная независимость от облачных API |

**Решение по этим — по запросу пользователя.** Если спросит "хочу больше ИИ для отказоустойчивости" — подключаем по очереди.

### Что делает Meta-Learner конкретно

LightGBM модель решает **один вопрос каждые 5-15 минут**:

> «На основе текущего состояния рынка — какая sub-стратегия (или их комбинация) даст наибольший risk-adjusted return в следующие 1-3 часа?»

**Output:** веса 5 sub-стратегий, сумма = 1.

Пример:
```python
{
    "trend_following": 0.45,    # сильный тренд → большой вес
    "mean_reversion": 0.10,
    "vol_breakout": 0.05,
    "xasset_momentum": 0.20,
    "funding_arbitrage": 0.20,  # пассивный слой всегда
}
```

**Features (~25-30 штук) на вход Meta-Learner:**
- Volatility regime: 5m/1h/4h ATR относительно 30-day median.
- BTC dominance change за 24h.
- Funding rate spreads между парами.
- Rolling Sharpe каждой sub-стратегии за 7/14/30 дней (саморефлексия).
- Time-of-day, day-of-week.
- News sentiment last hour (через Groq AI-Gate).
- Macro state (через Macro-sentinel).
- Cross-asset correlations.
- Volume / Open Interest ratios.

**Тренировка:** на 18+ месяцев исторических данных + 3-6 месяцев warm-up paper trading.

### Принципы разделения "ИИ vs система"

**ИИ решает (только это):**
1. Meta-Learner — веса каждой sub-стратегии в текущий момент.
2. Anomaly Detector — есть ли сейчас аномалия рынка (yes/no).
3. AI-Gate — есть ли red-flag в новостях (approve/veto).
4. Regime classifier — какой сейчас рыночный регим (3 класса).

**Система решает всё остальное:**
- Все 5 sub-стратегий (детерминированные правила).
- Stop-loss, take-profit (жёсткие лимиты).
- Position sizing (формула с весом от Meta-Learner).
- Глобальные риск-лимиты (GLOBAL_RISK_CAP).
- API-исполнение, retry, обработка частичных fills.
- Telegram UI, мониторинг, логирование.

### Fail-safe механики (обязательны)

1. **Если Meta-Learner показывает confidence < 0.5** → fallback на equal weights (0.2 каждой стратегии).
2. **Если Meta-Learner деградировал** (Sharpe < 0.3 на 30-day rolling) → отключить, остаются только sub-стратегии с равными весами.
3. **Если Anomaly Detector сработал** → размер всех новых позиций × 0.3 (защита от чёрных лебедей).
4. **Если AI-Gate ответил error 3+ раз подряд** → автоматический fallback в shadow mode на 1 час, новые сделки **разрешены без новостной проверки** (НЕ fail-closed как в текущей версии — здесь Meta-Learner главный).
5. **Закрытия работают БЕЗ ИИ** — stop-loss, take-profit, time-stop срабатывают сами.
6. **Auto-pause** при 3 LOSS подряд на паре (существующий механизм auto-block).

## Что нужно от пользователя — список

**Это критичный раздел.** Пользователь явно сказал «не ограничивай себя, что нужно — скажи».

### Минимально (для базовой версии)

| Что | Действие пользователя | Стоимость | Зачем |
|-----|----------------------|-----------|-------|
| ✅ OKX API ключи (demo + real) | **Уже есть** в `.env` | $0 | Доступ к OKX |
| ✅ Telegram Bot Token | **Уже есть** в `.env` | $0 | UI |
| ✅ Groq API Key | **Уже есть** в `.env` | $0 | LLM-слой |
| ✅ NewsAPI ключ | **Уже есть** в `.env` (через `news_engine.py`) | $0 | Источник новостей для AI-Gate |
| ✅ Сервер 147.45.76.76 | **Уже есть** | $0 | Деплой |

**Минимально нового добавлять не нужно.** Хватит для запуска базовой версии Multi-Strategy.

### Опционально (улучшит качество)

Если пользователь готов подключить — попросить эти ключи. Каждый — бесплатный free tier:

| # | Сервис | Что даст | Регистрация | Стоимость |
|---|--------|----------|-------------|-----------|
| 1 | **Hugging Face Inference API** | Backup LLM провайдер (если Groq упал) | https://huggingface.co/join | Free (1000 req/день) |
| 2 | **Cloudflare Workers AI** | Дополнительный sentiment слой | https://dash.cloudflare.com | Free (10k req/день) |
| 3 | **Together AI** | Альтернативный провайдер Llama/Qwen | https://api.together.xyz | Free $25 кредитов |
| 4 | **CryptoPanic API** | Качественные crypto-новости + sentiment | https://cryptopanic.com/developers/api | Free (300 req/день) |
| 5 | **Glassnode** (платный, рекомендуется) | On-chain метрики (BTC dominance, exchange flows) | https://glassnode.com | $30-100/мес — **ПОПРОСИТЬ ПОДКЛЮЧИТЬ** если хочется качества выше базы |
| 6 | **CoinAPI / Tardis.dev** (платный, опционально) | Order book history для будущих расширений | $300-500/мес | НЕ обязательно для Multi-Strategy |
| 7 | **OpenRouter** | Доступ к 200+ моделям через один API | https://openrouter.ai | Pay-per-use, есть бесплатные модели |
| 8 | **Google Gemini API** | Сильная мультимодальная модель | https://aistudio.google.com | Free (15 req/мин) |

**Что НЕ нужно подключать (даже если бесплатно):**
- OpenAI / Anthropic — слишком дорого для high-frequency вызовов в боте.
- AWS Bedrock — overkill для нашего масштаба.
- Любые подписочные сервисы "AI trading signals" — это маркетинг, а не источники данных.

### Если пользователь спросит "что бы ты добавила в первую очередь"

**Топ-3 рекомендации в порядке полезности:**

1. **CryptoPanic API** (free) — лучшие crypto-новости с sentiment-разметкой. Улучшит AI-Gate. Регистрация 2 минуты.
2. **Hugging Face** (free) — backup для Groq. Если Groq упадёт на час — система продолжит работать.
3. **Glassnode** ($30-100/мес) — единственный платный сервис, который реально нужен для quant-edge. On-chain данные (exchange flows, supply distribution) дают signal на 1-7 дней вперёд. Если бюджет позволяет — **подключать**.

**Что делать новой сессии:** в первом сообщении спросить пользователя, готов ли он подключить любой из этих сервисов. **Не предполагать**, что готов или не готов. Спросить явно.

## Что есть сейчас в репо (на момент handoff)

### Репо

- Default-ветка: `feat/zenith-control-ultimate`.
- Активная рабочая ветка: `feat/v3-tg-dashboard` (HEAD `ac25176`).
- Открыт PR #1 с UI-улучшениями (sparkline, прогресс-бары, EXPLAIN) + три handoff-коммита.
- Есть исследовательская ветка `chore/express-backtest-1y` (локально) с downloader OHLCV из OKX и кэшем за 1 год — переиспользовать!

### Известные факты

**Express backtest текущей `strategy_v2` за 1Y:** Total return -11.62%, Sharpe -0.84, MaxDD -17%, PF 0.76. Edge не подтверждён.

**Look-ahead bias в `strategy_v2`:** на 4H/1D в построении ctx. Документировано в `.agents/tasks/task-express-backtest-1y/2026-05-13-204230-review.md`. **Должно быть исправлено в Фазе 1.**

### Что НЕЛЬЗЯ трогать

- **Прод-сервер `147.45.76.76`** — пользователь деплоит сам.
- **9-кнопочное главное меню** Telegram-бота — утверждённый layout.
- **Существующие токены/ключи** в `.env` — все 8 ключей оставить.
- **AI_TRADE_GATE_MODE=active** — оставить.

### Что МОЖНО переиспользовать

**80% Telegram UI** (`telegram_bot.py`):
- `_card`, `_label`, `_fmt_num`, `_fmt_pct`, `_fmt_pnl`, `_progress_bar_10`, `_sparkline_8` — все хелперы.
- 9-кнопочное меню — оставить как есть.
- Все 11 карточек — переиспользовать с адаптацией наполнения.

**Risk-management слой** в `main.py`:
- `_sum_open_risk`, kill-switches, `GLOBAL_RISK_CAP`, `auto_block` — всё переиспользовать.

**Биржевой слой** `exchanges/okx.py`:
- `place_order_with_fallback`, `set_trading_stop`, `get_orderbook_top` — переиспользовать.

**Memory** `memory.py`:
- trades.db, `record_trade`, `get_per_symbol_stats`, `record_equity` — переиспользовать.
- Добавить новые таблицы для Meta-Learner training data (`meta_features`, `meta_labels`).

## Phased план разработки

### Фаза 0: Подготовка данных и инфраструктура (1-2 недели)

- Скачать 1m, 5m, 1h OHLCV за 2 года для 7 пар через OKX history-candles.
- Скачать funding rates за 2 года.
- Подготовить feature engineering pipeline (50+ features).
- Зафиксить look-ahead bias в `strategy_v2.py`.
- Перепрогнать express backtest для **честного** baseline.

**Чекпойнт:** после фикса look-ahead — какие реальные цифры strategy_v2? Если Sharpe всё ещё < 0 — она войдёт в ансамбль с маленьким весом, но это нормально.

### Фаза 1: Sub-стратегия 1 (Trend Following) — фиксы и валидация (1-2 недели)

- Walk-forward 5 окон на текущей `strategy_v2`.
- Параметрический sweep (Donchian length, ATR mult, ADX threshold).
- Найти оптимальные параметры на каждой паре.

**Чекпойнт:** OOS Sharpe должен быть >= 0.4 хотя бы на 3 из 7 пар. Если нет — стратегия слишком слаба, оставляем но с минимальным весом.

### Фаза 2: Sub-стратегия 2 (Mean Reversion) — доделка (2 недели)

- Доделать `strategy_v2_meanrevert.py`.
- Walk-forward валидация.

**Чекпойнт:** OOS Sharpe >= 0.5.

### Фаза 3: Sub-стратегии 3, 4 (Volatility Breakout, Cross-asset Momentum) — новый код (2-3 недели)

- Реализовать с нуля через `strategies/vol_breakout.py` и `strategies/xasset_momentum.py`.
- Walk-forward.

**Чекпойнт:** каждая OOS Sharpe >= 0.4.

### Фаза 4: Sub-стратегия 5 (Funding Arbitrage) — новый код (2 недели)

- Downloader funding rates.
- Логика delta-neutral позиций.
- Симуляция за 2 года.

**Чекпойнт:** funding-arb должна давать стабильные 8-15% годовых даже без других стратегий.

### Фаза 5: Meta-Learner (LightGBM) (2-3 недели)

- Подготовить training dataset: для каждого 5-минутного среза — фичи + актуальные ex-post returns каждой sub-стратегии.
- Обучение LightGBM на 18 месяцев данных.
- Walk-forward валидация (5 окон).
- Anomaly Detector тренировка.

**Чекпойнт:** ансамбль с Meta-Learner должен показывать Sharpe **выше**, чем любая отдельная sub-стратегия и чем equal-weighted ансамбль. Если нет — Meta-Learner не работает, deploy с equal-weights.

### Фаза 6: Ensemble Coordinator + Risk Integration (1-2 недели)

- Связать всё через `ensemble/coordinator.py`.
- Интеграция с existing risk manager.
- Подключить fail-safe механики.
- Подключить ML Explainer (Groq Qwen) для пояснений.

### Фаза 7: Telegram UI адаптация (2 недели)

См. отдельный раздел "Визуальный стиль" ниже. **Не менять 9-кнопочное меню.**

### Фаза 8: Paper trading на демо OKX (4-6 недель)

- $5,000 виртуальных USDT.
- Логирование всех решений Meta-Learner с контекстом.
- Еженедельные ревью результатов.

**Чекпойнт после 4 недель:** если Sharpe < 0.5 — выяснить почему, не двигаться в live.

### Фаза 9: Live с малой суммой (4-8 недель)

- $500-1000 на real OKX.
- Постепенное наращивание до полной суммы.

### Фаза 10: Опциональные расширения (после успешного запуска)

Включаются по запросу пользователя:
- On-chain features через Glassnode.
- Дополнительные sentiment-слои.
- Ollama локальные модели для backup.
- Расширение универсума пар (10+ вместо 7).

**Итого: 5-7 месяцев до production.** Это в 1.5-2 раза быстрее DL ensemble (там было 9-12 месяцев).

## Реалистичные ожидания

Из публикаций (López de Prado 2018, AQR Multi-Strategy, Two Sigma Spectrum, Bridgewater Pure Alpha):

| Сценарий | Доходность | Вероятность |
|----------|-----------|-------------|
| Pessimistic (Meta-Learner не нашёл edge) | 8-15% | 25% |
| **Realistic** | **18-28%** | **50%** |
| Good | 28-45% | 18% |
| Excellent | 45-70% | 5% |
| Outlier | 70%+ | 2% |

**Expected value: ~22% годовых при MaxDD ~15%.**

**Шанс достичь 40-50% годовых: ~20-25%.** Это не гарантия.

## Технические требования

### Pip-зависимости

```bash
pip install numpy>=1.24
pip install pandas>=2.0
pip install scikit-learn>=1.3   # IsolationForest, walk-forward utilities
pip install lightgbm>=4.0       # Meta-Learner
pip install joblib>=1.3         # сохранение моделей
```

**Это всё.** 5 пакетов. Никакого PyTorch, никакого TensorFlow, никакого RL. Никакого GPU.

### Compute

- **Тренировка Meta-Learner**: ~5-15 минут на CPU (8 ядер).
- **Inference**: <50ms на CPU, не нагружает.
- **Retrain каждые 2-3 месяца** (LightGBM не деградирует так быстро как нейросети).

### Никаких новых платных подписок не требуется

Базовая версия — на $0 дополнительных расходов. Опциональные сервисы (Glassnode, CoinAPI) — по решению пользователя.

## Адаптация Telegram UI

### Стилевые константы — НЕ МЕНЯТЬ

Эти значения уже захардкожены в `telegram_bot.py`. Их использовать как есть:

- `HR = "━" * 24` (U+2501).
- `SUBHR = "─" * 24` (U+2500).
- `_NBSP = "\u202f"` (узкий пробел).
- `_MINUS = "\u2212"` (типографский минус).
- Прогресс-бары `▰` / `▱`, длина 10.
- Sparkline `▁▂▃▄▅▆▇█`.
- Стрелки `LONG ↗`, `SHORT ↘`, PnL `▲ +x%` / `▼ −x%`.
- Точечные индикаторы 🟢🟡🔴⚪.
- Все карточки через `_card(title, emoji, body_lines)`.

### 9-кнопочное главное меню — НЕ МЕНЯТЬ

```
┌────────────────────┬────────────────────┐
│ 📊 СТАТУС          │ 📈 ПОЗИЦИИ         │
│ 🛡 AI-GATE         │ 🎯 РЕЖИМЫ          │
│ 🔍 ПОЧЕМУ МИМО?    │ 📝 ЛОГИ            │
│ 🤖 АНАЛИТИК        │ 🔑 КЛЮЧИ API       │
│  ⏯ СТАРТ/СТОП  ·  🚨 PANIC SELL          │
└─────────────────────────────────────────┘
```

`set_keyboard()` оставить как есть. Не трогать ни одну кнопку, ни один callback_id.

### Эмодзи и цвета — РАЗРЕШЕНО расширять

Пользователь явно разрешил использовать новые эмодзи и цвета на твоё усмотрение. Принципы:

- **ML-слои** в карточках:
  - `🌳` — LightGBM Meta-Learner (gradient boosting = деревья).
  - `🔮` — Anomaly Detector (предсказание аномалий).
  - `⚡` — быстрые sub-стратегии (Vol Breakout, Mean Revert).
  - `📊` — медленные sub-стратегии (Trend, Cross-asset, Funding).
- **ML-статусы**: `🤖 active`, `💤 idle`, `⚠️ degraded`, `🛠 retraining`, `❄️ frozen`, `🔁 rebalancing`.
- **Confidence-индикаторы** (расширенная палитра):
  - `🟩` ≥ 0.75 (high)
  - `🟢` 0.6–0.75 (ok)
  - `🟡` 0.45–0.6 (medium)
  - `🟠` 0.3–0.45 (low)
  - `🔴` < 0.3 (very low)
- **Стратегические события**: `🧪` (training), `🔬` (validation), `📈` (good), `📉` (bad), `🎯` (target hit).

**Принципы:**
1. Один эмодзи = одна семантика по всему боту.
2. Не перегружать строку (макс. один цветной + один тематический эмодзи).
3. Если добавляешь новый эмодзи — обнови helper и используй везде через него, не хардкодом.
4. Если сомневаешься — лучше меньше эмодзи, чем больше.

### Адаптация конкретных карточек

#### 📊 СТАТУС (`_handle_status`) — расширенный

Переиспользовать всё, что есть. **Добавить блок «Ensemble» перед «Режимы:»:**

```
🌳 Multi-Strategy Ensemble:
  Trend Follow    🟢 active   ▰▰▰▰▱▱▱▱▱▱  42%
  Mean Reversion  🟢 active   ▰▰▱▱▱▱▱▱▱▱  18%
  Vol Breakout    💤 standby  ▱▱▱▱▱▱▱▱▱▱  0%
  Cross-asset Mom 🟡 partial  ▰▱▱▱▱▱▱▱▱▱  10%
  Funding Arb     🟢 active   ▰▰▰▱▱▱▱▱▱▱  30%
─────────────────────────
  Meta-Learner    🟩 conf 0.82
  Regime          trending (BTC dom +1.2%)
  Anomaly         🟢 normal
─────────────────────────
  Ensemble Sharpe ▰▰▰▰▰▰▰▰▱▱  1.7 (30д OOS)
```

#### 📈 ПОЗИЦИИ (`_handle_positions`) — расширенный

Переиспользовать sparkline 15m·30 (FEAT-A). **Добавить строку «От стратегии»:**

```
🟢 BTC-USDT-SWAP  LONG ↗
  ▂▃▃▄▅▆▇█▇▆▅▆▇█▇▆  15m·30
  Стратегия    Trend Follow  conf 0.71
  Вход         63 240.0000
  Сейчас       63 815.5000
  PnL          ▲ 11.50 USDT
  PnL %        ▲ 0.91%
  TP           63 840.0000  (▲ 0.91%)    ← реальный TP на бирже
  Время        2ч 14м
  Стоп         62 950.0000  (▼ −0.46%)
```

#### 🎯 РЕЖИМЫ (`_handle_regimes`) — основная адаптация

Сейчас показывает рыночный режим по парам. **Расширить в три секции:**

```
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Режимы
━━━━━━━━━━━━━━━━━━━━━━━━
Рыночные регимы (по парам):
🟢 BTC-USDT-SWAP  Тренд    conf=82
🟡 ETH-USDT-SWAP  Боковик  conf=64
... (как сейчас)
─────────────────────────
🌳 Веса Meta-Learner:
  Trend Follow    ▰▰▰▰▱▱▱▱▱▱  42%
  Mean Reversion  ▰▰▱▱▱▱▱▱▱▱  18%
  Vol Breakout    ▱▱▱▱▱▱▱▱▱▱  0%
  Cross-asset Mom ▰▱▱▱▱▱▱▱▱▱  10%
  Funding Arb     ▰▰▰▱▱▱▱▱▱▱  30%
─────────────────────────
🔮 Anomaly Detector:
  Status       🟢 normal
  Score        0.18 / threshold 0.5
─────────────────────────
Performance стратегий (30д OOS):
  Trend Follow   Sharpe 1.4  WR 56%
  Mean Revert    Sharpe 0.9  WR 61%
  Vol Breakout   Sharpe 0.3  ❌ paused
  Cross-asset M  Sharpe 1.1  standby
  Funding Arb    Sharpe 1.8  stable
─────────────────────────
Обновлено   14:32 UTC
━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 🔍 ПОЧЕМУ МИМО? (`_handle_why`)

Переиспользовать. Добавить новые причины в `_FILTER_TAG_RU`:
- `meta_low_confidence` → "Meta-Learner: низкая уверенность (<0.5)"
- `meta_anomaly_detected` → "Anomaly Detector сработал"
- `meta_strategy_paused` → "Стратегия приостановлена (низкий Sharpe)"

#### 📝 ЛОГИ (`_handle_logs`)

Не менять. Добавить четвёртый фильтр `ensemble` для grep строк с тегом `[META]` / `[STRAT_X]` — отдельной кнопкой.

#### 🤖 АНАЛИТИК (`_handle_analyst`)

Не менять структуру. Добавить новые примеры:
```python
(CB_ANALYST_EX5, "Почему Meta-Learner выбрал Trend Follow?")
(CB_ANALYST_EX6, "Какая sub-стратегия лучше за месяц?")
```

Подключить **ML Explainer** (Groq Qwen) для развёрнутых ответов.

#### 🔑 КЛЮЧИ API (`_handle_keys_menu`)

Не менять список 8 ключей. Если пользователь добавит опциональные API (HuggingFace, Glassnode, CryptoPanic) — добавить кнопки замены этих ключей.

#### ⏯ СТАРТ/СТОП · 🚨 PANIC SELL

Не менять.

#### 🚫 ЗАПРЕТЫ

Переиспользовать 1:1, включая FEAT-B секцию «На грани авто-блока».

#### 📈 По парам

Переиспользовать. Добавить в детальную карточку:
```
Лучшая стратегия (30д)  Trend Follow · Sharpe 1.4
```

#### 📉 BACKTEST

Переписать наполнение под walk-forward Multi-Strategy. Кнопки `7д / 30д / 90д` оставить.

#### 🤖 GROQ

Не менять. Прогресс-бары квоты остаются.

#### Push-уведомления

Push при открытии — сохранить структуру. Добавить блок:
```
─────────────────────────
🌳 Meta-Learner:
  Стратегия    Trend Follow
  Confidence   0.71
  Regime       trending
─────────────────────────
```

Push при закрытии — новая карточка `🏁 СДЕЛКА ЗАКРЫТА` с разбором "ML был прав?".

## Контакт с пользователем

Пользователь общается на русском. Стиль: коротко, по делу, без вступлений и похвалы. Emoji допустимы только внутри UI продукта (Telegram), но не в самих ответах ассистента. Когда говорит «продолжай» — следующий разумный шаг без уточняющих вопросов. Когда говорит «как считаешь лучше» — принимать решение самостоятельно и показывать готовый результат.

**История эволюции выбора:**
- Сначала была текущая `strategy_v2` (trend-following с Donchian) — оказалась убыточной в express backtest (-12% за год).
- Я предложила 6 рекомендаций (funding-arb, stat arb, multi-strategy MM+MR, triangular arb, cross-asset momentum, DL ensemble).
- Пользователь сначала выбрал DL ensemble, потом передумал в пользу Multi-Strategy + Meta-filter после моего честного ответа, что Multi-Strategy лучше под его требования.
- **Текущий финальный выбор: Multi-Strategy Ensemble + Meta-Learning.**
- НЕ предлагать ему альтернативы заново.

## Первые шаги новой сессии

1. Прочитать `Khy18/.kiro/steering/zenith-control-v3.md`.
2. Прочитать этот файл целиком.
3. **Спросить пользователя про опциональные API** (CryptoPanic, HuggingFace, Glassnode) — готов ли подключить.
4. Подтвердить с пользователем готовность к 5-7 месяцам разработки.
5. Создать ветку `feat/multi-strategy-ensemble` от `feat/v3-tg-dashboard`.
6. **Делегировать Фазу 0** планировщику.

**Не начинать с кода.** Начать с подтверждения скоупа.

## Открытые вопросы для пользователя (задать в первом сообщении)

1. Готов ли подключить **CryptoPanic API** (бесплатный, улучшит AI-Gate)? Регистрация 2 минуты на https://cryptopanic.com/developers/api.
2. Готов ли подключить **Hugging Face Inference API** (бесплатный, backup для Groq)? Регистрация 2 минуты на https://huggingface.co/join.
3. Готов ли платить $30-100/мес за **Glassnode** (on-chain метрики)? Это **единственный** платный сервис, который реально нужен для quant edge. Не обязательно для базовой версии.
4. Нужно ли мерджить PR #1 (UI-улучшения) перед началом Multi-Strategy работы?
5. Готов ли к 5-7 месяцам разработки с поэтапными чекпойнтами?

## Что НЕ делать

- Не обещать 100%+ годовых.
- Не использовать параметры стратегий "из учебника" без walk-forward валидации.
- Не пропускать чекпойнты после каждой фазы.
- Не давать ИИ право управлять риском (Meta-Learner только корректирует **размер** через multiplier, не решает stop-loss).
- Не торопиться в live с реальными деньгами без 4+ недель paper trading.
- Не менять 9-кнопочное меню.
- Не предлагать пользователю переключиться обратно на DL ensemble или другие отвергнутые варианты.
- Не делегировать разработку без явного "да" пользователя.

## Контрольный чек-лист перед каждым релизом фазы

1. `python -m py_compile telegram_bot.py main.py memory.py config.py` — компилируется.
2. `grep -n 'set_keyboard' telegram_bot.py` — ровно одно определение, ровно 5 рядов кнопок (`[2,2,2,2,1]`).
3. `grep -n 'HR = "━" \* 24' telegram_bot.py` — константа на месте.
4. `grep -n 'def _card\|def _label\|def _fmt_num\|def _fmt_pct\|def _progress_bar_10\|def _sparkline_8\|def _status_dot\|def _dir_arrow' telegram_bot.py` — все восемь хелперов на месте.
5. Для каждой адаптированной карточки — реальная сверка через grep по якорям. **Не показывать пользователю mockup, который не соответствует коду.** Это steering-рулинг из прошлой сессии.

## Приоритет файлов handoff

**Использовать ТОЛЬКО** `Khy18/.kiro/handoff/NEXT_SESSION_PROMPT_MULTI_STRATEGY.md` (этот файл).

**Игнорировать** `Khy18/.kiro/handoff/NEXT_SESSION_PROMPT_DL.md` (устарел, пользователь передумал).

---

Конец handoff. Удачи следующему агенту.
