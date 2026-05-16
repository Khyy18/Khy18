# AI Office

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![License MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Tests](https://img.shields.io/badge/tests-233%20passing-brightgreen.svg)

**AI Office** - это "карманная компания": команда из 8 AI-агентов, работающая как полноценный виртуальный офис в Telegram Mini App. Каждый агент специализируется на своей области (разработка, дизайн, QA, DevOps, аналитика, маркетинг, финансы), может делегировать задачи коллегам, составлять планы и работать проактивно.

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│              Telegram Mini App (React + Vite)                  │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP / WebSocket
                             ▼
┌──────────────────────────────────────────────────────────────┐
│          FastAPI + Middleware (Auth, Logging, CORS)            │
│  15 route modules | WebSocket | Prometheus metrics            │
└────────────────────────────┬─────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────────┐
│  8 AI Agents   │  │   Proactive    │  │   Plugin System    │
│  (LangGraph)   │  │   Scheduler    │  │  (manifest.yaml)   │
│  + Tools       │  │                │  │                    │
└────────┬───────┘  └────────────────┘  └────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│   PostgreSQL   |      Redis      |    OpenAI / Anthropic     │
└──────────────────────────────────────────────────────────────┘
```

## Возможности

- **8 специализированных агентов** с уникальными инструментами и ролями
- **Делегирование задач** между агентами с полной трассировкой
- **Streaming-ответы** через WebSocket в реальном времени
- **Kanban-доска** задач с drag-and-drop
- **Проактивное поведение:** ежедневный стендап, недельные отчеты, алерты
- **Plugin system** для расширения без изменения кода
- **Multi-tenant** архитектура с ролевой моделью
- **Multi-LLM** с fallback (OpenAI, Anthropic, Groq)
- **Budget control** с дневным лимитом и rate limiting
- **Интеграции:** GitHub, Linear, Notion
- **Prometheus-метрики** и structured logging

## Быстрый старт

```bash
# 1. Клонировать и настроить
git clone <repository-url>
cp .env.example .env
# Заполнить OPENAI_API_KEY и TELEGRAM_BOT_TOKEN в .env

# 2. Запустить
docker compose -f ai_office/deploy/docker-compose.yml up -d

# 3. Открыть Mini App в Telegram
```

## Тесты

```bash
python -m pytest ai_office/tests/ -q
```

## Документация

| Документ | Описание |
|----------|----------|
| [Руководство пользователя](docs/USER_GUIDE.md) | Описание агентов, интерфейса, FAQ |
| [Руководство разработчика](docs/DEVELOPER_GUIDE.md) | Архитектура, добавление агентов/инструментов, деплой |
| [API Reference](docs/API_REFERENCE.md) | Все эндпоинты, WebSocket, аутентификация |

## Стек технологий

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), LangGraph
- **Frontend:** React, Vite, TailwindCSS, TypeScript
- **Database:** PostgreSQL 16, Redis 7
- **AI:** OpenAI, Anthropic, Groq (multi-provider с fallback)
- **Deploy:** Docker Compose, Nginx, Alembic
- **Telegram:** Pyrogram, Mini App SDK

## Скриншоты

<!-- TODO: добавить скриншоты Mini App -->

## Contributing

1. Fork репозитория
2. Создайте feature branch: `git checkout -b feature/my-feature`
3. Внесите изменения и добавьте тесты
4. Убедитесь что тесты проходят: `python -m pytest ai_office/tests/ -q`
5. Commit и push: `git push origin feature/my-feature`
6. Создайте Pull Request

### Правила

- Весь пользовательский текст на русском языке
- Идентификаторы (переменные, функции, классы) на английском
- Каждый новый tool должен иметь `_log_activity()` helper
- Покрытие тестами обязательно для новых эндпоинтов

## License

MIT
