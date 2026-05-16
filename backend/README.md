# Backend API - Бухгалтерия детского сада

REST API для бухгалтерского учета детского сада. Предоставляет HTTP-эндпоинты для всех функций Telegram-бота.

## Установка

```bash
pip install -r backend/requirements.txt
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | URL базы данных | `sqlite+aiosqlite:///./bot.db` |
| `BOT_TOKEN` | Токен Telegram-бота | `test-bot-token` |
| `SECRET_KEY` | Секретный ключ для Bearer-авторизации | `change-me-in-production` |
| `CORS_ORIGINS` | Разрешенные CORS-домены (через запятую) | `*` |
| `GROQ_API_KEY` | API-ключ Groq | - |

## Запуск

```bash
uvicorn backend.app:app --reload --port 8000
```

API будет доступен по адресу: http://localhost:8000

Документация Swagger: http://localhost:8000/docs

## Эндпоинты

### Калькуляторы

- `POST /api/v1/salary/calculate` - Расчет заработной платы
- `POST /api/v1/vacation/calculate` - Расчет отпускных
- `POST /api/v1/sick/calculate` - Расчет больничного

### Сотрудники

- `GET /api/v1/employees` - Список сотрудников
- `POST /api/v1/employees` - Добавить сотрудника
- `DELETE /api/v1/employees/{id}` - Удалить сотрудника

### Дети

- `GET /api/v1/children` - Список детей
- `POST /api/v1/children` - Добавить ребенка
- `DELETE /api/v1/children/{id}` - Удалить ребенка

### Табель

- `POST /api/v1/timesheet/mark` - Добавить отметку
- `GET /api/v1/timesheet/summary/{employee_id}?year=2024&month=3` - Сводка за месяц

### Журнал операций

- `POST /api/v1/journal` - Добавить запись
- `GET /api/v1/journal` - Список записей (фильтр: `start_date`, `end_date`)
- `GET /api/v1/journal/totals` - Итоги за период

### Платежи

- `POST /api/v1/payments/generate` - Сформировать платежное поручение

### Напоминания

- `GET /api/v1/reminders` - Список напоминаний
- `POST /api/v1/reminders/toggle` - Включить/выключить напоминание
- `GET /api/v1/reminders/upcoming` - Ближайшие дедлайны

### КБК

- `GET /api/v1/kbk/search?q=запрос` - Поиск КБК
- `GET /api/v1/kbk/popular` - Популярные КБК

## Авторизация

API поддерживает два метода:

1. **Bearer Token** - заголовок `Authorization: Bearer <SECRET_KEY>`
2. **Telegram WebApp** - заголовок `X-Telegram-Init-Data` с валидным initData

## Тесты

```bash
python3 -m pytest backend/tests/ -v
```
