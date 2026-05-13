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

- `AI_TRADE_GATE_MODE=active` во всех трёх пресетах агрессивности (Консервативно/Средне/Агрессивно).
- **Без shadow-режима на 7-14 дней** — это явное требование пользователя.
- **Fail-CLOSED** при `gate.verdict=error`: блокирует сделку и шлёт push.
- Rate-limit на fail-CLOSED уведомление: 1 уведомление / 5 минут / пара (через `notify_trade_blocked_by_gate_error`).

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

- **Никаких новых pip-пакетов**. Только stdlib + уже установленное (`aiohttp`, `requests`).
- Если требуется фичу реализовать без новой зависимости — реализуем своими руками или отказываемся от фичи.

## Git workflow

- Все изменения — на ветке `feat/v3-tg-dashboard`.
- Default-ветка репо — `feat/zenith-control-ultimate` (не `main`!). PR всегда в неё.
- **Никогда не использовать `git push` напрямую** — только через `github_push_to_remote` MCP tool.
- Коммиты на русском в формате `feat(v3-tg): ...` / `fix(v3-tg): ...`.

## Watchdog (фича №19)

- **НЕ делать**. Пользователь явно исключил из плана.

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
