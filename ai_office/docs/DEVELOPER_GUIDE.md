# AI Office - Руководство разработчика

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────────┐
│                     Telegram Mini App (React)                     │
│                  Vite + TailwindCSS + WebSocket                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP / WS
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI (api/main.py)                        │
│  Routes: agents, tasks, activity, plans, delegations, usage,     │
│  metrics, dashboard, templates, feedback, delegation_trace,      │
│  plugins, admin, health, status                                  │
│  Middleware: TelegramAuth, RequestLogging, CORS                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   Agent Engine   │ │   Proactive      │ │   Plugin Loader  │
│   (LangGraph)    │ │   Scheduler      │ │   (manifest.yaml)│
│                  │ │                  │ │                  │
│ AgentRegistry    │ │ Standup          │ │ Auto-discovery   │
│ 8 agents         │ │ Weekly report    │ │ Hot reload       │
│ Tools + Memory   │ │ Overdue alerts   │ │                  │
└────────┬─────────┘ │ Health checks    │ └──────────────────┘
         │           └──────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│                    Tools Layer (langchain @tool)               │
│  task_tools, code_tools, search_tools, design_tools,         │
│  analytics_tools, qa_tools, devops_tools, github_tools,      │
│  marketing_tools, finance_tools, delegation, memory_tools,   │
│  planning_tools, voice_tools, file_tools                     │
└───────────────────────────────┬──────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   PostgreSQL     │ │      Redis       │ │   External APIs  │
│   (SQLAlchemy    │ │   (cache,        │ │   OpenAI, GitHub │
│    async 2.0)    │ │    rate limit)   │ │   Linear, Notion │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Поток данных

1. Пользователь открывает Mini App в Telegram
2. Frontend подключается к API и WebSocket
3. Запрос проходит через middleware (auth, logging)
4. Router направляет к нужному handler'у
5. Handler создает задачу / вызывает агента
6. Агент использует инструменты (tools) для выполнения
7. Результат сохраняется в БД, событие отправляется через WebSocket
8. Frontend обновляет UI в реальном времени

---

## Структура проекта

```
ai_office/
├── agents/                    # Конфигурации агентов
│   ├── __init__.py           # Регистрация всех агентов
│   ├── base.py               # AgentConfig dataclass
│   ├── registry.py           # AgentRegistry (singleton)
│   ├── alice.py              # Alice - PM
│   ├── sam.py                # Sam - Developer
│   ├── max.py                # Max - Designer
│   ├── eva.py                # Eva - Analyst
│   ├── leo.py                # Leo - QA
│   ├── nova.py               # Nova - DevOps
│   ├── marketing.py          # Iris - Marketing
│   └── finance.py            # Oscar - Finance
├── api/                       # FastAPI application
│   ├── main.py               # App factory, lifespan, routers
│   ├── middleware.py          # Telegram auth middleware
│   ├── observability.py       # Request logging, metrics
│   ├── schemas.py            # Pydantic response/request models
│   ├── websocket.py          # WebSocket manager
│   └── routes/               # Endpoint modules
│       ├── agents.py         # /api/agents
│       ├── tasks.py          # /api/tasks
│       ├── activity.py       # /api/activity
│       ├── plans.py          # /api/plans
│       ├── delegations.py    # /api/delegations
│       ├── usage.py          # /api/usage
│       ├── metrics.py        # /api/metrics
│       ├── dashboard.py      # /api/dashboard
│       ├── templates.py      # /api/templates
│       ├── feedback.py       # /api/feedback
│       ├── delegation_trace.py # /api/delegations/{id}/trace
│       ├── plugins.py        # /api/plugins
│       └── admin.py          # /api/admin
├── core/                      # Ядро системы
│   ├── config.py             # Settings (pydantic-settings)
│   ├── database.py           # async SQLAlchemy engine + session
│   ├── models.py             # ORM модели (Task, Agent, etc.)
│   ├── logging.py            # Настройка логирования
│   ├── cache.py              # Redis cache wrapper
│   ├── rate_limiter.py       # Rate limiter + budget tracker
│   ├── memory.py             # Agent memory (ChromaDB)
│   ├── scheduler.py          # Proactive task scheduler
│   └── permissions.py        # Role-based access control
├── tools/                     # Langchain tool modules
│   ├── task_tools.py         # Управление задачами
│   ├── code_tools.py         # Выполнение и ревью кода
│   ├── search_tools.py       # Веб-поиск
│   ├── design_tools.py       # Инструменты дизайна
│   ├── analytics_tools.py    # Аналитика и отчеты
│   ├── qa_tools.py           # QA-инструменты
│   ├── devops_tools.py       # DevOps-инструменты
│   ├── github_tools.py       # GitHub API
│   ├── marketing_tools.py    # Маркетинг
│   ├── finance_tools.py      # Финансы
│   ├── delegation.py         # Делегирование между агентами
│   ├── memory_tools.py       # Запоминание / вспоминание
│   ├── planning_tools.py     # Планирование (create_plan)
│   ├── voice_tools.py        # Голосовые сообщения (Whisper/TTS)
│   └── file_tools.py         # Обработка файлов
├── plugins/                   # Директория плагинов
│   ├── loader.py             # Загрузчик плагинов
│   └── <plugin_name>/        # Плагин = директория
│       ├── manifest.yaml     # Описание плагина
│       └── tools.py          # Инструменты плагина
├── telegram/                  # Telegram клиент (Pyrogram)
├── frontend/                  # React + Vite + TailwindCSS
├── deploy/                    # Docker, nginx, docker-compose
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf
├── tests/                     # pytest + pytest-asyncio
│   ├── conftest.py           # Fixtures (in-memory SQLite)
│   ├── test_api.py
│   ├── test_agents.py
│   ├── test_tools.py
│   └── ...
├── docs/                      # Документация
├── requirements.txt           # Python зависимости
└── main.py                    # Entrypoint
```

---

## Как добавить нового агента

### Способ 1: Через код (agents/)

1. Создайте файл `ai_office/agents/<name>.py`:

```python
"""Конфигурация агента <Name> - <роль>."""

from ai_office.agents.base import AgentConfig
from ai_office.tools.task_tools import update_task_status, get_active_tasks
from ai_office.tools.delegation import delegate_to_agent

SYSTEM_PROMPT = """Ты - <Name>, <описание роли> в AI Office.

Твои обязанности:
- ...

Правила:
- Всегда отвечай на русском языке
- ...
"""

<name>_config = AgentConfig(
    name="<name>",
    role="<Role Title>",
    system_prompt=SYSTEM_PROMPT,
    tools=[update_task_status, get_active_tasks, delegate_to_agent],
)
```

2. Зарегистрируйте в `ai_office/agents/__init__.py`:

```python
from ai_office.agents.<name> import <name>_config

registry.register(<name>_config)
```

3. Готово! Агент доступен через API и может получать делегированные задачи.

### Способ 2: Через плагин (plugins/)

1. Создайте директорию `ai_office/plugins/<plugin_name>/`

2. Создайте `manifest.yaml`:

```yaml
name: my_agent
display_name: "My Agent"
role: "Custom Specialist"
system_prompt: |
  Ты - специалист по ...
  Правила:
  - Всегда отвечай на русском языке
model: gpt-4o-mini
tools:
  - my_custom_tool
  - another_tool
```

3. Создайте `tools.py`:

```python
"""Инструменты плагина."""
from langchain_core.tools import tool

@tool
def my_custom_tool(query: str) -> str:
    """Описание инструмента."""
    # Реализация
    return "result"
```

4. Перезагрузите плагины: `POST /api/plugins/reload`

---

## Как добавить новый инструмент (tool)

1. Создайте или откройте файл в `ai_office/tools/`:

```python
"""Описание модуля инструментов."""

import logging
from langchain_core.tools import tool
from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog

logger = logging.getLogger(__name__)


async def _log_activity(agent_id: int, action_type: str, description: str):
    """Записать активность в БД."""
    async with async_session() as session:
        log = ActivityLog(
            agent_id=agent_id,
            action_type=action_type,
            action_description=description,
        )
        session.add(log)
        await session.commit()


@tool
def my_new_tool(param: str) -> str:
    """Описание инструмента для LLM (будет видно агенту)."""
    # Реализация
    result = f"Обработано: {param}"
    return result
```

2. Добавьте инструмент в конфигурацию нужного агента:

```python
# В файле agents/<agent>.py
from ai_office.tools.<module> import my_new_tool

<agent>_config = AgentConfig(
    ...
    tools=[..., my_new_tool],
)
```

**Паттерн `_log_activity`:** каждый модуль инструментов использует helper-функцию `_log_activity()` для записи действий агента в лог активности. Это обеспечивает единообразную трассировку.

---

## Как добавить новую интеграцию

1. Добавьте переменные окружения в `core/config.py`:

```python
class Settings(BaseSettings):
    ...
    my_service_api_key: str = Field(default="", description="API ключ MyService")
    sync_to_my_service: bool = Field(default=False, description="Синхронизация в MyService")
```

2. Создайте модуль инструментов `tools/my_service_tools.py` с функциями API.

3. Добавьте тест подключения в `api/routes/admin.py` (endpoint `POST /api/admin/integrations/test`).

4. Назначьте инструменты соответствующему агенту.

---

## Как запустить тесты

```bash
# Все тесты
python -m pytest ai_office/tests/ -q

# Конкретный файл
python -m pytest ai_office/tests/test_api.py -v

# С coverage
python -m pytest ai_office/tests/ --cov=ai_office --cov-report=term-missing
```

Тесты используют in-memory SQLite (фикстура `async_session` в `conftest.py`), поэтому не требуют внешней БД.

---

## Деплой

### Docker Compose (рекомендуемый)

```bash
# Сборка и запуск
docker compose -f ai_office/deploy/docker-compose.yml up -d

# Логи
docker compose -f ai_office/deploy/docker-compose.yml logs -f api

# Остановка
docker compose -f ai_office/deploy/docker-compose.yml down
```

Состав сервисов:
- **api** - FastAPI приложение (порт 8000)
- **postgres** - PostgreSQL 16 (основная БД)
- **redis** - Redis 7 (кэш, rate limiting)
- **nginx** - Nginx (реверс-прокси, раздача фронтенда, порт 80)

### Миграции (Alembic)

```bash
# Создать миграцию
alembic revision --autogenerate -m "описание"

# Применить миграции
alembic upgrade head
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `OPENAI_API_KEY` | `""` | API ключ OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | Модель OpenAI |
| `ANTHROPIC_API_KEY` | `""` | API ключ Anthropic |
| `GROQ_API_KEY` | `""` | API ключ Groq |
| `LLM_PROVIDERS` | `openai,anthropic,groq` | Порядок провайдеров (fallback chain) |
| `LLM_MAX_RETRIES` | `3` | Макс. количество повторов на провайдер |
| `DAILY_BUDGET_USD` | `10.0` | Дневной бюджет в USD |
| `GLOBAL_RPM_LIMIT` | `100` | Глобальный лимит запросов/мин |
| `AGENT_RPM_LIMIT` | `20` | Лимит запросов/мин на агента |
| `ENABLE_RATE_LIMITER` | `true` | Включить rate limiter |
| `LOG_LEVEL` | `INFO` | Уровень логирования (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | `json` | Формат логов: json или text |
| `ENABLE_PROACTIVE` | `true` | Включить проактивные задачи |
| `STANDUP_HOUR` | `9` | Час ежедневного стендапа (UTC) |
| `WEEKLY_REPORT_DAY` | `monday` | День недельного отчета |
| `OVERDUE_CHECK_INTERVAL_HOURS` | `4` | Интервал проверки просроченных задач (часы) |
| `HEALTH_CHECK_INTERVAL_HOURS` | `1` | Интервал проверки здоровья системы (часы) |
| `TELEGRAM_API_ID` | `0` | Telegram API ID |
| `TELEGRAM_API_HASH` | `""` | Telegram API Hash |
| `TELEGRAM_BOT_TOKEN` | `""` | Токен Telegram бота |
| `TARGET_CHAT_ID` | `0` | ID целевого чата |
| `GITHUB_TOKEN` | `""` | GitHub Personal Access Token |
| `LINEAR_API_KEY` | `""` | API ключ Linear |
| `SYNC_TO_LINEAR` | `false` | Синхронизация задач в Linear |
| `NOTION_API_KEY` | `""` | API ключ Notion |
| `NOTION_DATABASE_ID` | `""` | ID базы данных Notion |
| `SYNC_TO_NOTION` | `false` | Синхронизация в Notion |
| `WHISPER_MODEL` | `whisper-1` | Модель Whisper для транскрипции |
| `TTS_MODEL` | `tts-1` | Модель TTS для синтеза речи |
| `VOICE_RESPONSES` | `false` | Отвечать голосовыми сообщениями |
| `SKIP_TELEGRAM_AUTH` | `true` | Пропуск аутентификации (dev-режим) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./ai_office.db` | URL подключения к базе данных |
| `REDIS_URL` | `""` | URL Redis (опционально) |

---

## Конвенции кода

- **Язык интерфейса:** весь пользовательский текст на русском
- **Идентификаторы:** на английском (имена переменных, функций, классов)
- **Async:** все DB-операции через `async/await` с SQLAlchemy 2.0
- **Tools:** декоратор `@tool` из `langchain_core.tools`, каждый модуль имеет `_log_activity()`
- **Тесты:** pytest + pytest-asyncio, фикстуры в `conftest.py`
- **Форматирование:** стандартное для Python (PEP 8)
