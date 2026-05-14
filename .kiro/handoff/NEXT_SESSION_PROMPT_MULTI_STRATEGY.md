# Next session: Multi-Strategy Ensemble + Meta-Learning

> **Версия 2** (синхронизирована со steering, обновлены LLM-маршрутизация и fail-safes).
> Прочти этот файл и `Khy18/.kiro/steering/zenith-control-v3.md` ПЕРЕД любыми действиями.
> **Игнорируй** `NEXT_SESSION_PROMPT_DL.md` — устаревшая итерация.

## Финальный выбор архитектуры

**Multi-Strategy Ensemble + Meta-Learning** (5 sub-стратегий + LightGBM + Anomaly Detector + LLM-слой). Решение зафиксировано после 8 итераций обсуждения, **альтернативы не предлагать**.

## Параметры запуска

- Биржа: **OKX** (один API).
- Счёт: **демо** (`IS_TESTNET=true`), $5 000 виртуальных USDT.
- Универсум: 7 пар из `config.SYMBOLS` (BTC/ETH/SOL/BNB/XRP/DOGE/AVAX-USDT-SWAP). Только для **Cross-asset Momentum** расширить до 15–20 пар на этапе ranking.
- Hold time: 30 мин — 4 ч. Сделок/день: 5–15.
- Цель: **realistic 12–18% годовых при MaxDD 12–18%** (P50). Апсайд 22%+ при MaxDD ~15% (P75). 22% — не median, а P75. Не обещать пользователю «гарантированно 22%».

## Канонические термины

Использовать **только эти** в коде, логах, UI и документации:

| Термин | Что это |
|---|---|
| **Meta-Learner** | LightGBM-модель, выдающая веса 5 sub-стратегий |
| **Ensemble Coordinator** | Слой `ensemble/coordinator.py` — правила + Meta-Learner вместе |
| **sub-стратегия** | Одна из 5 детерминированных (Trend / MR / VB / XAM / FA) |
| **LLMRouter** | Маршрутизатор LLM-вызовов между провайдерами |

Канонические теги логов: `[META]`, `[ENSEMBLE]`, `[STRAT_TF/MR/VB/XAM/FA]`, `[GATE]`, `[ANOMALY]`, `[REGIME]`, `[MACRO]`, `[CRITIC]`, `[ROUTER]`.

## High-level схема

```
[OKX websocket+REST · 7 пар]
        ↓
[News engine: NewsAPI + CryptoPanic]
        ↓
[News dedup (MinHash, локально)]
        ↓
[Keyword pre-filter (red-flag слова)]   ← AI-Gate вызывается только при срабатывании
        ↓
[Feature pipeline · 50+ features]
        ↓
   ┌────┬─────────┬──────────┬────────────┬──────────┐
   ▼    ▼         ▼          ▼            ▼          ▼
[Trend][Mean    [Vol       [Cross-asset][Funding   ← 5 sub-стратегий (правила)
 Follow Revert] Breakout]   Momentum]    Arbitrage]
   │    │         │          │            │
   └────┴────┬────┴──────────┴────────────┘
             ▼
   ┌──────────────────────────┐
   │  Meta-Learner (LightGBM) │  → веса 5 стратегий, conf
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Anomaly Detector (IF)   │  → множитель размера 0.3–1.0
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Ensemble Coordinator    │  → агрегация сигналов
   │  hard caps: MR≤25%, *≤50%│
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  AI-Gate (LLM, кэш 15м)  │  → veto на red-flag в новостях
   │  через LLMRouter         │
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Risk Manager            │  → GLOBAL_RISK_CAP, kill, auto-block
   └──────────────────────────┘
             ↓ APPROVED
   ┌──────────────────────────┐
   │  Order Engine (OKX)      │
   └──────────────────────────┘
             ↓
   ┌──────────────────────────┐
   │  Telegram Bot (UI)       │
   └──────────────────────────┘

Offline (раз в день/неделю):
   [Daily Critic] → daily_critique.db
   [Weekly Stats Report] → push в Telegram
   [Cross-strategy correlation] → раз в час, авто-даунвейт
```

## 5 sub-стратегий

| # | Стратегия | Файл | Состояние | Сложность |
|---|---|---|---|---|
| 1 | Trend Following (Donchian + EMA + ATR) | `Khy18/strategy_v2.py` | есть, фикс look-ahead | 1/5 |
| 2 | Mean Reversion (Bollinger + RSI + Z-score) | `Khy18/strategy_v2_meanrevert.py` | скелет 391 стр | 2/5 |
| 3 | Volatility Breakout (Keltner + ATR expansion) | `Khy18/strategies/vol_breakout.py` | новый, ~250 стр | 2/5 |
| 4 | Cross-asset Momentum (ranking 15–20 пар по 7d return) | `Khy18/strategies/xasset_momentum.py` | новый, ~200 стр | 2/5 |
| 5 | Funding Arbitrage (delta-neutral perpetual+spot) | `Khy18/strategies/funding_arb.py` | новый + downloader, ~500 стр | 3/5 |

**Все 5 — детерминированные правила, не ML.** Прозрачные, тестируемые юнит-тестами.

### Funding Arbitrage — конкретная механика

Реализация **OKX-only delta-neutral** (без cross-exchange, чтобы не подключать вторую биржу):
- short perpetual `*-USDT-SWAP` ↔ long spot `*-USDT` (OKX spot).
- Триггер входа: `funding_rate > 0.05%` за период (8h), скользящее окно из последних 3 funding events `> 0.03%`.
- Выход: `funding_rate <= 0.01%` ИЛИ скользящий return позиции отрицателен 2 часа подряд.
- Учёт издержек: spot taker fee + perpetual taker fee + slippage по orderbook L2 + ребалансировка spot-leg при отклонении дельты > 1%.
- Ожидаемая доходность после costs: 3–7% годовых на капитал, выделенный под FA.
- Размер leg'а: от 5% до 25% от total капитала, динамически по `funding_rate`.

## ИИ-компоненты (полный список)

### Группа A: локальные ML и численные слои (ядро)

| Слой | Технология | Когда работает | Что решает |
|---|---|---|---|
| **Meta-Learner** | LightGBM (CPU) | каждые 5 мин | веса 5 sub-стратегий + confidence |
| **Anomaly Detector** | IsolationForest | каждые 5 мин | множитель размера 0.3–1.0 |
| **News dedup** | MinHash или TF-IDF cosine | при каждом news poll | склейка дублей >0.85 similarity |
| **Keyword pre-filter** | regex по словарю | при каждом news poll | вызывать ли AI-Gate |
| **Cross-strategy correlation** | numpy | раз в час | автоснижение веса при corr > 0.7 |
| **Weekly Stats Report** | numpy + sqlite | воскресенье | push с отчётом по фактам |

**Все локальные слои работают на CPU, без сети, ~$0.**

### Группа B: LLM-слои через `LLMRouter`

Каждый слот имеет primary + fallback. Подробнее — в разделе «LLM Budget & Multi-Provider Routing».

| Слот | Primary | Fallback | Частота | Задача |
|---|---|---|---|---|
| `ai_gate` | Groq Llama-8B | Cerebras gpt-oss-120b | при keyword hit | veto на red-flag |
| `regime` | Cerebras gpt-oss-120b | Groq Llama-8B | каждый час | TRENDING/RANGING/CRISIS |
| `macro` | Google Gemini-2.5-Flash | Groq Llama-8B | каждый час | FOMC/CPI blackout |
| `critic` | OpenRouter DeepSeek-V3 (free) | Groq Llama-70B | раз в сутки (offline) | разбор сделок дня |
| `analyst` | Groq Llama-3.3-70B | Gemini-2.5-Flash | по тапу в Telegram | разговор |
| `postmortem` | OpenRouter DeepSeek-R1 (free) | Groq Llama-70B | раз в неделю | weekly report |
| `explainer` | Groq Qwen-72B | Gemini-2.5-Flash | по тапу | пояснение решений |
| `embeddings` | локально `sentence-transformers` (BAAI/bge-small-en-v1.5) | — | по необходимости | для dedup и similarity |

> **Ревизия Май 2026:** убраны Together AI (free tier полностью отменён, минимум $5 prepaid) и HuggingFace Inference (free квоты порезаны до неюзабельного уровня). Embeddings переведены на локальный `sentence-transformers` (CPU). Analyst и Explainer fallback'и переведены на Gemini (1500 RPD free).

### Группа C: что НЕ добавлять (даже бесплатно)

- **OpenAI / Anthropic API** — overkill для structured-задач.
- **Локальная Ollama** на сервере 147.45.76.76 — мало RAM, тормозит торговый цикл.
- **Multi-agent оркестрация** (CrewAI/AutoGen/LangGraph) — 200–500 ms latency, бессмысленно для realtime.
- **Realtime Adversarial Critic перед каждой сделкой** — заменён на Daily Offline Critic. Снимает 70B-нагрузку с hot-path.
- **LLM-based self-reflection раз в неделю** — заменён на Weekly Stats Report (чистый Python). Сухая статистика лучше для саморефлексии.

## LLM Budget & Multi-Provider Routing

### Узкое место — TPM на 70B, не RPD

Расчёт нагрузки **до оптимизаций** показал ~2 016 запросов/день к AI-Gate (на каждый сигнал × 7 пар × каждые 5 мин). При средней длине промпта 1500 токенов это ~50 000 TPM пиково — выше лимита.

### 6 техник оптимизации (все обязательны)

1. **Кэш AI-Gate с TTL=15 мин**, ключ = `hash(latest_news_timestamps + macro_state)`. Экономия 75–85%.
2. **Batching**: один промпт на все 7 пар с JSON-выходом. Экономия 7×.
3. **Keyword pre-filter** перед LLM: словарь red-flag слов (`hack, exploit, SEC, lawsuit, halt, depeg, bankrupt, drain, freeze, rugpull`). Если нет совпадений — verdict=approve без вызова LLM. Экономия 60–80%.
4. **News dedup** через MinHash перед AI-Gate. Экономия 60–70% входных токенов.
5. **Cascade 8B → 70B**: дешёвая 8B на pre-check, эскалация на 70B только в зоне неопределённости conf 0.3–0.7. Экономия 60–70% вызовов 70B.
6. **Reduce frequency Regime** до 1 ч (вместо 5–15 мин из v1). Экономия 4×.

### Реальная нагрузка после оптимизаций

| Слой | req/день | tier | Запас |
|---|---|---|---|
| AI-Gate (cache+batch+keyword) | ~30 | 8B | 480× |
| Regime (1ч) | 24 | 8B | 600× |
| Macro (1ч) | 24 | Gemini | 60× |
| Daily Critic (1 batch/день) | 1 | DeepSeek | comfortable |
| Analyst | ~30 | 70B | 30× |
| Explainer | ~20 | Qwen | 50× |
| Postmortem | ~1 | DeepSeek-R1 | comfortable |

Запас огромный. Можно увеличить универсум до 20+ пар без переплат.

### LLMRouter — контракт класса

```python
class LLMRouter:
    """Маршрутизация LLM-вызовов с failover и quota tracking."""

    SLOT_ROUTING = {
        "ai_gate":    [("groq", "llama-3.1-8b-instant"),
                       ("cerebras", "gpt-oss-120b")],
        "regime":     [("cerebras", "gpt-oss-120b"),
                       ("groq", "llama-3.1-8b-instant")],
        "macro":      [("google", "gemini-2.5-flash"),
                       ("groq", "llama-3.1-8b-instant")],
        "critic":     [("openrouter", "deepseek/deepseek-chat-v3:free"),
                       ("groq", "llama-3.3-70b-versatile")],
        "analyst":    [("groq", "llama-3.3-70b-versatile"),
                       ("google", "gemini-2.5-flash")],
        "postmortem": [("openrouter", "deepseek/deepseek-r1:free"),
                       ("groq", "llama-3.3-70b-versatile")],
        "explainer":  [("groq", "qwen-2.5-72b-instruct"),
                       ("google", "gemini-2.5-flash")],
        # Embeddings — локально sentence-transformers, без сети.
        # "embeddings" слот не маршрутизируется через LLMRouter.
    }

    def call(self, slot: str, prompt: str, **kwargs) -> dict:
        """
        1. lookup providers for slot in priority order
        2. for each: check quota_tracker и circuit_breaker
        3. on success → log to llm_calls table, return
        4. on 5xx/timeout/quota → mark provider degraded, try next
        5. on all-failed → raise RouterAllFailed (caller handles fallback)
        """
        ...
```

Таблица `llm_calls` (SQLite):
```
id | ts | slot | provider | model | tokens_in | tokens_out
   | latency_ms | status | fallback_reason | cache_hit
```

### Failover policy в Telegram

- На каждое переключение **не пушить**. Накапливать.
- Раз в час: если за час было ≥3 fallback на одном слоте → один push с агрегатом.
- Если все провайдеры упали 3+ раз подряд → системный push «🛑 LLM degraded» + AI-Gate в shadow на 1 час.

## Что делает Meta-Learner конкретно

LightGBM решает один вопрос каждые 5 минут:

> «Какая комбинация sub-стратегий даст лучший risk-adjusted return в следующие 1–3 часа?»

**Output:** веса 5 sub-стратегий (sum=1) + confidence.

**Hard caps (не зависят от Meta-Learner):**
- любая стратегия ≤ 50%;
- Mean Reversion ≤ 25% (защита от bull-trend);
- Vol Breakout ≤ 30%;
- если после нормализации сумма ≠ 1 → перенормировать.

### Features (~25–30) на вход Meta-Learner

- Volatility regime: 5m/1h/4h ATR относительно 30-day median.
- BTC dominance change за 24h.
- Funding rate spreads между парами.
- Rolling Sharpe каждой sub-стратегии за 7/14/30 дней.
- Time-of-day, day-of-week.
- News sentiment last hour (через AI-Gate verdict).
- Macro state (через Macro-sentinel).
- Cross-asset correlations.
- Volume / Open Interest ratios.

### Тренировка и валидация

**Data split (зафиксирован):**
- **Train:** 2023-01-01 → 2024-06-30 (18 мес).
- **Validation:** 2024-07-01 → 2024-12-31 (6 мес).
- **Test (out-of-sample):** 2025-01-01 → 2025-04-30 (4 мес).
- **Paper trading:** 2025-05-01 → ... (4–6 нед).
- **Embargo:** 7 дней между train/val и val/test, чтобы не утекали overlapping bars.
- **Walk-forward:** 12 окон по 1 мес test step через train 6 мес. Окно сдвигается каждый месяц.

**Repro-seed:** `random_state=42` явно в LightGBM, IsolationForest, всех train_test_split.

**Ретрейн в production:** **раз в месяц** (не раз в 2–3 как в первой версии). Crypto concept drift быстрее equity.

## Принципы разделения «ИИ vs система»

**ИИ решает (только это):**
1. Meta-Learner — веса каждой sub-стратегии в текущий момент.
2. Anomaly Detector — есть ли сейчас аномалия рынка (yes/no).
3. AI-Gate — есть ли red-flag в новостях (approve/veto).
4. Regime classifier — какой рыночный регим (3 класса).

**Система решает всё остальное:**
- 5 sub-стратегий (детерминированные правила).
- Stop-loss, take-profit (жёсткие лимиты, физически на бирже).
- Position sizing (формула с весом от Meta-Learner и множителем от Anomaly).
- Глобальные риск-лимиты (`GLOBAL_RISK_CAP`).
- API-исполнение, retry, обработка частичных fills.
- Telegram UI, мониторинг, логирование.

## Fail-safe механики

1. **Confidence Meta-Learner < 0.5** → fallback на equal weights (0.2 каждой).
2. **Rolling Sharpe Meta-Learner < 0.3 на 30-day OOS** → отключить Meta-Learner, equal weights.
3. **Anomaly score выше threshold** → размер всех новых позиций × 0.3.
4. **AI-Gate primary провайдер недоступен** → автопереключение через `LLMRouter` на backup. При полном падении всех провайдеров 3+ раз подряд → shadow на 1 час, новые сделки разрешены без news-проверки.
5. **Закрытия работают БЕЗ ИИ** — stop-loss и take-profit физически на бирже.
6. **Auto-pause при 3 LOSS подряд** на паре (существующий механизм).
7. **Cross-strategy correlation > 0.7 за 30 дней** → авто-даунвейт более слабой стратегии.
8. **Drift monitoring**: PSI по фичам Meta-Learner раз в неделю; PSI > 0.25 → push «фичи дрифтуют, переобучение».
9. **Корректность модели**: при failure загрузки LightGBM → старт с equal_weights, push в Telegram.

## Технические требования

### Pip-зависимости (фиксированы)

```
numpy>=1.24,<2
pandas>=2.0,<3
scikit-learn>=1.3,<2
lightgbm>=4.0,<5
joblib>=1.3,<2
```

**Это всё.** Минорные версии пиннуть, breaking changes не должны приехать.

Запрещено: PyTorch, TensorFlow, JAX, RL-фреймворки, multi-agent оркестрация. См. steering.

### Compute

- Тренировка Meta-Learner: 5–15 мин на CPU (8 ядер).
- Inference: <50 ms на CPU.
- Ретрейн: раз в месяц.

### Платных подписок не требуется

Базовая версия — $0. Glassnode ($30–100/мес) — единственный реально полезный платный сервис, подключать после успешного paper trading, если бюджет позволяет.

## Что нужно от пользователя

### Минимально (уже есть)

| Что | Состояние |
|---|---|
| OKX API ключи (demo + real) | ✅ в `.env` |
| Telegram Bot Token | ✅ в `.env` |
| Groq API Key | ✅ в `.env` |
| NewsAPI Key | ✅ в `.env` |
| Сервер 147.45.76.76 | ✅ |

### Опциональные API-ключи (5 штук, все бесплатные)

Регистрация суммарно ~15 минут. **Без них** система работает на одном Groq → единая точка отказа. **С ними** — failover + специализация моделей.

| # | Сервис | URL | Время | Free tier | Зачем |
|---|---|---|---|---|---|
| 1 | Cerebras | https://cloud.cerebras.ai | 2 мин | 14400 RPD | drop-in замена Groq |
| 2 | Google AI Studio | https://aistudio.google.com | 2 мин | 1500 RPD | Gemini-2.0-Flash для Macro |
| 3 | OpenRouter | https://openrouter.ai | 3 мин | бесплатные модели | DeepSeek, Nemotron |
| 4 | Hugging Face | https://huggingface.co/join | 2 мин | 1000 req/день | embeddings + backup |
| 5 | CryptoPanic | https://cryptopanic.com/developers/api | 2 мин | 300 req/день | crypto-новости |

После регистрации поля попадают в `.env` (см. `.env.example`).

### Платный (опционально)

- **Glassnode** ($30–100/мес) — on-chain метрики. Подключать после paper trading.

### Что НЕ подключать

- OpenAI / Anthropic API.
- AWS Bedrock.
- AI trading signals подписки.
- CoinAPI / Tardis.dev — не нужно для Multi-Strategy.

## Что есть сейчас в репо

- Default-ветка: `feat/zenith-control-ultimate`.
- Активная: `feat/v3-tg-dashboard`.
- Открыт PR #1 с UI-улучшениями (sparkline, прогресс-бары, EXPLAIN) + handoff-коммиты.
- Локальная исследовательская ветка `chore/express-backtest-1y`: downloader OHLCV из OKX + кэш за 1 год — переиспользовать в Фазе 0.

### Известные факты

- Express backtest текущей `strategy_v2` за 1Y: Total return −11.62%, Sharpe −0.84, MaxDD −17%, PF 0.76. Edge не подтверждён.
- Look-ahead bias в `strategy_v2` на 4H/1D — задокументировано в `.agents/tasks/task-express-backtest-1y/2026-05-13-204230-review.md`. **Фикс в Фазе 1.**

### Что НЕЛЬЗЯ трогать

См. steering. Кратко: прод 147.45.76.76, 9-кнопочное меню, существующие токены, формулы хелперов UI.

### Что МОЖНО переиспользовать

**Telegram UI 80%** (`telegram_bot.py`): все хелперы (`_card`, `_label`, `_fmt_num`, `_fmt_pct`, `_fmt_pnl`, `_progress_bar_10`, `_sparkline_8`, `_status_dot`, `_dir_arrow`), 9-кнопочное меню, 11 карточек.

**Risk-management** (`main.py`): `_sum_open_risk`, kill-switches, `GLOBAL_RISK_CAP`, auto-block.

**Биржевой слой** (`exchanges/okx.py`): `place_order_with_fallback`, `set_trading_stop`, `get_orderbook_top`.

**Memory** (`memory.py`): trades.db, `record_trade`, `get_per_symbol_stats`, `record_equity`, таблица `symbol_blocks`.

**Новые таблицы под Multi-Strategy:**
- `meta_features` — снимки фичей перед каждым решением Meta-Learner.
- `meta_predictions` — фичи + prediction + outcome для drift monitoring.
- `llm_calls` — все вызовы LLM с провайдером, latency, fallback_reason.
- `llm_cache` — TTL-кэш ответов LLM.
- `daily_critique` — результаты Daily Offline Critic.

**Расширение `trades.db`** (новые колонки):
- `strategy_attribution` — какая sub-стратегия инициировала.
- `meta_weights` — JSON со снимком весов на момент входа.
- `gate_verdict` — approve / veto / approve_cached / approve_no_news.
- `anomaly_score` — на момент входа.

## Phased план разработки

**Realistic timeline: 7–9 месяцев** до live (5–7 — оптимистичный best-case).

### Фаза 0: подготовка данных и инфраструктуры (2–3 нед)

- Скачать 1m, 5m, 1h OHLCV за 2 года для 7 пар через OKX history-candles + 15–20 пар для XAM.
- Скачать funding rates за 2 года.
- Реализовать `LLMRouter` (~200 стр) + `llm_calls`/`llm_cache` таблицы.
- News dedup (MinHash) + Keyword pre-filter.
- Добавить колонки `strategy_attribution`, `meta_weights`, `gate_verdict`, `anomaly_score` в `trades.db`.
- Зафиксить look-ahead bias в `strategy_v2.py`.
- Перепрогнать **honest** express backtest с реальными costs (taker fee + slippage по L2 + funding).

**Чекпойнт:** baseline после фикса look-ahead. Если Sharpe всё ещё < 0 — стратегия войдёт в ансамбль с минимальным весом.

### Фаза 1: Trend Following — фиксы и валидация (2 нед)

- Walk-forward 12 окон по описанному split.
- Параметрический sweep (Donchian length, ATR mult, ADX threshold) с защитой от p-hacking (cross-validated grid).

**Чекпойнт:** OOS Sharpe ≥ 0.4 хотя бы на 3 из 7 пар. Если нет — оставляем с минимальным весом.

### Фаза 2: Mean Reversion — доделка (2 нед)

- Доделать `strategy_v2_meanrevert.py`.
- Walk-forward.

**Чекпойнт:** OOS Sharpe ≥ 0.5 хотя бы на 3 из 7 пар.

### Фаза 3: Vol Breakout + Cross-asset Momentum (3 нед)

- Реализовать с нуля.
- XAM: ranking на 15–20 пар, не на 7.
- Walk-forward для каждой.

**Чекпойнт:** каждая OOS Sharpe ≥ 0.4.

### Фаза 4: Funding Arbitrage (3 нед)

- Downloader funding rates (OKX endpoint `/api/v5/public/funding-rate-history`).
- Логика delta-neutral perpetual + spot leg.
- Симуляция 2 года с честным учётом издержек ребалансировки.

**Чекпойнт:** funding-arb даёт стабильные 3–7% годовых на выделенный leg, MaxDD < 8%.

### Фаза 5: Meta-Learner (LightGBM) (3–4 нед)

- Подготовить training dataset: для каждого 5-минутного среза — фичи + ex-post returns каждой sub-стратегии.
- Тренировка LightGBM.
- Walk-forward валидация (12 окон).
- Anomaly Detector тренировка.
- PSI baseline для drift monitoring.

**Чекпойнт:** ансамбль с Meta-Learner показывает Sharpe **выше**, чем любая отдельная sub-стратегия и чем equal-weighted ансамбль. Если нет — deploy с equal-weights.

### Фаза 6: Ensemble Coordinator + Risk Integration (2 нед)

- Связать всё через `ensemble/coordinator.py`.
- Интеграция с risk manager.
- Подключить fail-safe механики (все 9).
- Cross-strategy correlation monitor.
- Drift monitoring (PSI weekly).

### Фаза 7: Telegram UI адаптация (2 нед)

См. раздел «Адаптация Telegram UI». **Не менять 9-кнопочное меню.**

### Фаза 8: Paper trading на демо OKX (4–6 нед)

- $5 000 виртуальных USDT.
- Полное логирование решений Meta-Learner.
- Еженедельные ревью.
- Daily Critic + Weekly Stats Report включены.

**Чекпойнт после 4 нед:** если Sharpe < 0.5 — выяснить причину, не идти в live.

### Фаза 9: Live с малой суммой (4–8 нед)

- $500–1000 на real OKX.
- Постепенное наращивание.

### Фаза 10: опциональные расширения

- On-chain через Glassnode.
- Дополнительные sentiment-слои.
- Расширение универсума до 10+ пар (для всех стратегий, не только XAM).

## Адаптация Telegram UI

### Стилевые константы — НЕ МЕНЯТЬ

Все значения уже захардкожены в `telegram_bot.py`. Использовать как есть:

- `HR = "━" * 24` (U+2501).
- `SUBHR = "─" * 24` (U+2500).
- `_NBSP = "\u202f"`, `_MINUS = "\u2212"`.
- Прогресс-бары `▰▱`, длина 10.
- Sparkline `▁▂▃▄▅▆▇█`.
- `LONG ↗`, `SHORT ↘`, PnL `▲ +x%` / `▼ −x%`.
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

### Эмодзи и цвета — расширенная палитра (одобрено пользователем)

- ML-слои:
  - `🌳` — Meta-Learner (LightGBM).
  - `🔮` — Anomaly Detector.
  - `⚡` — быстрые sub-стратегии (VB, MR).
  - `📊` — медленные (TF, XAM, FA).
  - `🛰` — LLMRouter / провайдеры.
- Статусы: `🤖 active`, `💤 idle`, `⚠️ degraded`, `🛠 retraining`, `❄️ frozen`, `🔁 rebalancing`.
- Confidence: `🟩` ≥0.75 · `🟢` 0.6–0.75 · `🟡` 0.45–0.6 · `🟠` 0.3–0.45 · `🔴` <0.3.
- События: `🧪` training, `🔬` validation, `📈` good, `📉` bad, `🎯` target hit.

Принципы: один эмодзи = одна семантика; макс. один цветной + один тематический в строке; новый эмодзи только через helper.

### Адаптация конкретных карточек

#### 📊 СТАТУС — расширенный

Добавить блок «Ensemble» перед «Режимы:»:

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
  Anomaly         🟢 normal (0.18)
─────────────────────────
🛰 LLMRouter:
  Groq         🟢 ok (2/14400)
  Cerebras     🟢 ok (1/14400)
  Gemini       🟢 ok (1/1500)
  OpenRouter   🟢 ok
  HF           🟢 ok
─────────────────────────
  Ensemble Sharpe ▰▰▰▰▰▰▰▰▱▱  1.7 (30д OOS)
```

#### 📈 ПОЗИЦИИ — расширенный

Добавить строку «Стратегия» в карточку позиции:

```
🟢 BTC-USDT-SWAP  LONG ↗
  ▂▃▃▄▅▆▇█▇▆▅▆▇█▇▆  15m·30
  Стратегия    Trend Follow  conf 0.71
  Вход         63 240.0000
  Сейчас       63 815.5000
  PnL          ▲ 11.50 USDT
  PnL %        ▲ 0.91%
  TP           63 840.0000  (▲ 0.91%)
  Время        2ч 14м
  Стоп         62 950.0000  (▼ −0.46%)
```

#### 🎯 РЕЖИМЫ — основная адаптация

Три секции:

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

#### 🔍 ПОЧЕМУ МИМО? — добавить причины

`_FILTER_TAG_RU` пополнить:
- `meta_low_confidence` → "Meta-Learner: низкая уверенность (<0.5)"
- `meta_anomaly_detected` → "Anomaly Detector сработал"
- `meta_strategy_paused` → "Стратегия приостановлена (низкий Sharpe)"
- `meta_weight_capped` → "Hard cap веса стратегии"
- `gate_router_unavailable` → "LLMRouter: все провайдеры недоступны"

#### 📝 ЛОГИ

Добавить четвёртый фильтр `ensemble` для grep строк с тегами `[META] / [ENSEMBLE] / [STRAT_*] / [ROUTER]`.

#### 🤖 АНАЛИТИК

Добавить примеры:
```python
(CB_ANALYST_EX5, "Почему Meta-Learner выбрал Trend Follow?")
(CB_ANALYST_EX6, "Какая sub-стратегия лучше за месяц?")
(CB_ANALYST_EX7, "Покажи отчёт Daily Critic за вчера.")
```

#### 🔑 КЛЮЧИ API

К существующим 8 ключам добавить кнопки управления новыми (Cerebras, Google, OpenRouter, HF, CryptoPanic, Glassnode, Together).

#### 🚫 ЗАПРЕТЫ, 📈 По парам, 📉 BACKTEST, 🤖 GROQ, ⏯ СТАРТ/СТОП, 🚨 PANIC SELL

Не менять структуру. По парам — добавить «Лучшая стратегия (30д)». BACKTEST — переписать наполнение под walk-forward Multi-Strategy.

#### Push-уведомления

Push при открытии — добавить блок:
```
─────────────────────────
🌳 Meta-Learner:
  Стратегия    Trend Follow
  Confidence   0.71
  Regime       trending
─────────────────────────
```

Push при закрытии — новая карточка `🏁 СДЕЛКА ЗАКРЫТА` с разбором "ML был прав?".

Push при failover LLMRouter — раз в час с агрегатом, не на каждый вызов.

## Первые шаги новой сессии

1. Прочитать `Khy18/.kiro/steering/zenith-control-v3.md`.
2. Прочитать этот файл целиком.
3. Спросить пользователя про опциональные API-ключи (5 штук) — готов ли регистрировать.
4. Подтвердить с пользователем готовность к 7–9 месяцам разработки.
5. Принять решение по PR #1 (мерджить ли перед стартом ветки).
6. Создать ветку `feat/multi-strategy-ensemble` от `feat/v3-tg-dashboard`.
7. Делегировать Фазу 0 планировщику.

**Не начинать с кода.** Сначала подтверждение скоупа.

## Открытые вопросы (задать в первом сообщении)

1. Готов зарегистрировать **5 опциональных API** (Cerebras, Google, OpenRouter, HF, CryptoPanic) — все бесплатные, ~15 мин?
2. Готов ли платить $30–100/мес за **Glassnode** (после успешного paper trading, не сейчас)?
3. Мерджить **PR #1** в `feat/zenith-control-ultimate` перед стартом ветки `feat/multi-strategy-ensemble`?
4. Подтверждаешь готовность к **7–9 месяцам** разработки с поэтапными чекпойнтами?
5. Расширять универсум до **15–20 пар только для Cross-asset Momentum**, или для всех стратегий сразу?

## Контрольный чек-лист перед каждым релизом фазы

1. `python -m py_compile telegram_bot.py main.py memory.py config.py` — компилируется.
2. `grep -n 'set_keyboard' telegram_bot.py` — ровно одно определение, ровно 5 рядов кнопок (`[2,2,2,2,1]`).
3. `grep -n 'HR = "━" \* 24' telegram_bot.py` — константа на месте.
4. `grep -n 'def _card\|def _label\|def _fmt_num\|def _fmt_pct\|def _progress_bar_10\|def _sparkline_8\|def _status_dot\|def _dir_arrow' telegram_bot.py` — все восемь хелперов.
5. Для каждой адаптированной карточки — реальная сверка через grep по якорям. **Не показывать пользователю mockup, который не соответствует коду.**

## Что НЕ делать

- Не обещать 100%+ годовых. Realistic 12–18% (P50), апсайд 22%+ (P75).
- Не использовать параметры стратегий "из учебника" без walk-forward.
- Не пропускать чекпойнты после фаз.
- Не давать ИИ право на stop-loss.
- Не идти в live без 4+ нед paper trading.
- Не менять 9-кнопочное меню, не менять стилевые константы UI.
- Не предлагать вернуться на DL ensemble или другие отвергнутые варианты.

---

Конец handoff.
