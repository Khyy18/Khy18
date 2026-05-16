# AI Office - Docker Deployment

## Требования

- Docker >= 24.0
- Docker Compose >= 2.20
- Минимум 2 GB RAM
- 10 GB свободного места на диске

## Быстрый старт

```bash
# 1. Перейти в директорию deploy
cd ai_office/deploy

# 2. Создать файл окружения
cp .env.example .env

# 3. Заполнить переменные (обязательно: API ключи, Telegram токен, пароль БД)
nano .env

# 4. Запустить все сервисы
docker-compose up -d

# 5. Проверить статус
docker-compose ps
```

Приложение будет доступно:
- Frontend: http://localhost
- API: http://localhost/api/
- WebSocket: ws://localhost/api/ws

## Конфигурация

| Переменная | Описание | По умолчанию |
|---|---|---|
| `POSTGRES_DB` | Имя базы данных | `ai_office` |
| `POSTGRES_USER` | Пользователь БД | `ai_office` |
| `POSTGRES_PASSWORD` | Пароль БД | `changeme` |
| `DATABASE_URL` | Строка подключения | `postgresql+asyncpg://...` |
| `OPENAI_API_KEY` | API ключ OpenAI | - |
| `ANTHROPIC_API_KEY` | API ключ Anthropic | - |
| `GROQ_API_KEY` | API ключ Groq | - |
| `LLM_PROVIDERS` | Порядок провайдеров | `openai,anthropic,groq` |
| `DAILY_BUDGET_USD` | Дневной лимит расходов | `10.0` |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - |
| `TELEGRAM_CHAT_ID` | Chat ID владельца | - |
| `ENABLE_PROACTIVE` | Проактивное расписание | `true` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `LOG_FORMAT` | Формат логов (json/text) | `json` |

## Архитектура

```
                    +----------+
                    |  Nginx   |  :80
                    +----+-----+
                         |
              +----------+----------+
              |                     |
        Static Files          Proxy /api/
        (Frontend)                  |
                            +------+------+
                            |   FastAPI   |  :8000
                            |   + Telegram|
                            |   + Scheduler|
                            +------+------+
                                   |
                    +--------------+--------------+
                    |                             |
              +-----+-----+              +-------+-------+
              | PostgreSQL |              |   ChromaDB    |
              |  :5432     |              |  (volume)     |
              +-----------+              +---------------+
```

## Обслуживание

### Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Только API
docker-compose logs -f api

# Последние 100 строк
docker-compose logs --tail=100 api
```

### Резервное копирование PostgreSQL

```bash
# Создать дамп
docker-compose exec postgres pg_dump -U ai_office ai_office > backup_$(date +%Y%m%d).sql

# Восстановить из дампа
docker-compose exec -T postgres psql -U ai_office ai_office < backup_20240101.sql
```

### Обновление

```bash
# Пересобрать и перезапустить
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Перезапуск отдельного сервиса

```bash
docker-compose restart api
docker-compose restart nginx
```

## Решение проблем

### API не запускается

```bash
# Проверить логи
docker-compose logs api

# Частые причины:
# - Не заполнены обязательные переменные в .env
# - PostgreSQL еще не готов (подождите 10-15 секунд)
# - Порт 8000 занят другим процессом
```

### PostgreSQL не запускается

```bash
# Проверить логи
docker-compose logs postgres

# Сбросить данные (ВНИМАНИЕ: удалит все данные!)
docker-compose down
rm -rf data/postgres
docker-compose up -d
```

### Nginx возвращает 502

```bash
# Убедиться что API запущен
docker-compose ps api

# Проверить что API отвечает
docker-compose exec api curl -s http://localhost:8000/api/health
```

### WebSocket не подключается

Убедитесь что в nginx.conf корректно настроены заголовки Upgrade.
Проверьте что клиент подключается к `ws://your-domain/api/ws`.

### Недостаточно памяти

ChromaDB может потреблять много RAM при большом количестве документов.
Рекомендуется минимум 2 GB RAM для стабильной работы.
