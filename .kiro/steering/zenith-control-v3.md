# Zenith-Control v3 — правила репозитория

Эти правила специфичны для этого репо и должны соблюдаться во всех будущих изменениях.

## Прод-сервер

- **IP**: `147.45.76.76`
- **Никогда не трогать прод напрямую**. Все правки делаются в локальном клоне, пользователь сам деплоит командой:
  ```bash
  ssh root@147.45.76.76
  cd <path>/Khy18
  git fetch origin && git checkout feat/v3-tg-dashboard && git pull
  systemctl restart zenith-control
  ```

## Токены и .env

- `TELEGRAM_TOKEN`, `OKX_API_KEY`, `GROQ_API_KEY` — общие с v1-ботом, **не менять, не ротировать**.
- v1 остановлен пользователем; токены v3 = токены v1.
- При записи в `.env` использовать `_write_env_var` (атомарная запись через tmp + `os.replace`).
- Экспорт `.env` через бота **всегда маскирует секреты** (заменяет на `***`).

## AI-Gate

**Текущая политика (v1, до Multi-Strategy):**
- `AI_TRADE_GATE_MODE=active` во всех трёх пресетах агрессивности (Консервативно/Средне/Агрессивно).
- **Без shadow-режима на 7-14 дней** — это явное требование пользователя.
- **Fail-CLOSED** при `gate.verdict=error`: блокирует сделку и шлёт push.
- Rate-limit на fail-CLOSED уведомление: 1 уведомление / 5 минут / пара (через `notify_trade_blocked_by_gate_error`).

**Политика под Multi-Strategy Ensemble (вступает в силу с веткой `feat/multi-strategy-ensemble`):**
- AI-Gate перестаёт быть единственным фильтром — он один из слоёв ансамбля. Главный ИИ — LightGBM Meta-Learner.
- Вызов AI-Gate происходит **только при срабатывании keyword pre-filter** (red-flag слова в новостях) или при запросе от Macro-sentinel.
- При success — verdict кешируется в SQLite на 15 минут (ключ = hash от свежих заголовков + macro state).
- При 5xx/timeout/quota от primary-провайдера → автопереключение через `LLMRouter` на backup-провайдер (Cerebras → OpenRouter → HF). См. handoff раздел "LLM Budget & Multi-Provider Routing".
- Если **все** провайдеры недоступны 3+ раза подряд → fallback в shadow на 1 час, новые сделки проходят без news-проверки. Это безопасно: Meta-Learner и Risk Manager продолжают работать.
- Push при degradation (раз в час, не на каждый вызов).

## UI / стилистика

- **Весь UI и все push-уведомления — на русском**.
- Главное меню — **9 кнопок** (4 ряда по 2 + 1 широкая снизу `⏯ СТАРТ/СТОП · 🚨 PANIC SELL`). Этот layout утверждён, не менять без явной команды.
- Дизайн: горизонтальные разделители `━━━` (24 символа), числа с разделителем тысяч U+202F и истинным минусом U+2212, точечные индикаторы 🟢🔴🟡⚪, направление `LONG ↗` / `SHORT ↘`, PnL `▲+x%` / `▼−x%`, прогресс-бары `▰▰▱▱▱▱▱▱▱▱`.
- Все карточки строятся через единый хелпер `_card(title, emoji, body_lines)`.
- Числа форматируются через `_fmt_num`, проценты через `_fmt_pct`, PnL через `_fmt_pnl`.
- Кнопки минимальные, без лишних эмодзи кроме особых (`⏯`, `🚨`, `🤖`, `🛡`).

## Авто-блок символов

- После **3 LOSS подряд** на одной паре — автоматический блок.
- Авто-разблок **на первом WIN** или через **24 часа**.
- Таблица `symbol_blocks` в SQLite. Хелпер `is_symbol_blocked(symbol)` вызывается **первым** в `_process_symbol` (до стратегии и AI-Gate).
- Manual-блоки: длительности 1ч / 6ч / 24ч / 7 дней / Бессрочно.

## Зависимости

**Базовая политика (v1):**
- **Никаких новых pip-пакетов** для UI/риск-логики/телеграм-бота. Только stdlib + уже установленное (`aiohttp`, `requests`).
- Если требуется фичу UI/risk реализовать без новой зависимости — реализуем своими руками или отказываемся от фичи.

**Исключение под Multi-Strategy Ensemble:**
- Разрешён ML-стек: `numpy>=1.24`, `pandas>=2.0`, `scikit-learn>=1.3,<2`, `lightgbm>=4.0,<5`, `joblib>=1.3`. Только эти пять пакетов.
- Запрещено: PyTorch, TensorFlow, JAX, любой RL (stable-baselines3 и т.п.), любые фреймворки multi-agent оркестрации (CrewAI, AutoGen, LangGraph). Причины — в handoff.
- Любой новый пакет вне этого списка — только через явное согласование с пользователем.
- В `requirements.txt` минорные версии пиннятся (`>=X.Y,<X+1`) чтобы breaking changes не приехали с обновлением.

## Git workflow

- Все изменения — на ветке `feat/v3-tg-dashboard`.
- Default-ветка репо — `feat/zenith-control-ultimate` (не `main`!). PR всегда в неё.
- **Никогда не использовать `git push` напрямую** — только через `github_push_to_remote` MCP tool.
- Коммиты на русском в формате `feat(v3-tg): ...` / `fix(v3-tg): ...`.

## Watchdog (фича №19)

- **НЕ делать**. Пользователь явно исключил из плана.

## LLM-провайдеры и API-ключи (Multi-Strategy)

- Один Groq-ключ — единая точка отказа. Production-конфиг использует **5 LLM-провайдеров** через `LLMRouter`:
  - **Groq** (primary): AI-Gate, Analyst, ML Explainer.
  - **Cerebras** (drop-in замена Groq): Regime classifier primary, AI-Gate backup.
  - **Google AI Studio** (Gemini-2.0-Flash): Macro-sentinel (long-context для FOMC).
  - **OpenRouter** (DeepSeek-V3, Nemotron): Daily Offline Critic, Postmortem.
  - **Hugging Face Inference**: embeddings (news dedup), backup для Explainer.
- Все ключи опциональны и бесплатны (free tier). Без них — fallback на Groq, при его падении система деградирует к equal-weights.
- Канонический термин: **Meta-Learner** (LightGBM-модель) и **Ensemble Coordinator** (правила + Meta-Learner вместе). Использовать ТОЛЬКО эти два термина в коде, тегах логов (`[META]`, `[ENSEMBLE]`), UI и документации. Никаких "Meta-filter", "meta-обучаемый ИИ-фильтр" и т.п.
- Канонические теги логов: `[META]` (Meta-Learner), `[ENSEMBLE]` (Coordinator), `[STRAT_TF/MR/VB/XAM/FA]` (sub-стратегии), `[GATE]`, `[ANOMALY]`, `[REGIME]`, `[MACRO]`, `[CRITIC]`, `[ROUTER]`.

## ML-стек: hard caps и fail-safes (Multi-Strategy)

- **Веса sub-стратегий**: hard cap 50% на любую одну стратегию, hard cap 25% на Mean Reversion (защита от bull-trend market).
- **Confidence Meta-Learner < 0.5** → fallback на equal weights (0.2 каждой).
- **Rolling Sharpe Meta-Learner < 0.3 на 30-day** → отключить Meta-Learner, equal weights.
- **Anomaly score > threshold** → множитель размера всех новых позиций × 0.3.
- **Stop-loss всегда физически на бирже**, не зависит от ИИ.
- **Ретрейн Meta-Learner — раз в месяц** (не раз в 2-3 как в первой версии handoff). Crypto concept drift быстрее.
- **Repro-seed**: `random_state=42` явно указывать в LightGBM, IsolationForest, train/val split.

## Файлы и где что лежит

- `Khy18/main.py` — `_process_symbol`, push-уведомления, integration с авто-блоком.
- `Khy18/telegram_bot.py` — весь UI, callback-роутинг, FSM-состояния, хелперы визуала, 9-кнопочное меню.
- `Khy18/config.py` — флаги `NOTIFY_ON_TRADE_OPEN`, `NOTIFY_ON_GATE_ERROR_BLOCK`, `AUTO_BLOCK_LOSS_STREAK`, `AUTO_BLOCK_DURATION_HOURS`.
- `Khy18/memory.py` — `get_symbol_stats_30d`, `get_per_symbol_stats`, `is_symbol_blocked`, таблица `symbol_blocks`.
- `Khy18/ai_trade_gate.py` — `_build_prompt(historical_context=...)`.
- `Khy18/ai_groq.py` — парсинг `x-ratelimit-*`, обновление снапшота квоты.
- `Khy18/ai_analyst.py` — FSM-чат с аналитиком.
- `Khy18/backtester/` — backtest, используется этапом D из Telegram.
- `Khy18/.agents/tasks/task-v3-tg-multi-update/` — артефакты планировщика, ревью v1+v2.
