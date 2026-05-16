# AI Office - API Reference

Base URL: `http://localhost:8000`

## Аутентификация

Все эндпоинты (кроме `/api/health`, `/api/ws`, `/api/metrics`) требуют аутентификации через Telegram initData.

### Заголовок

```
X-Telegram-Init-Data: <initData string>
```

### Формат initData

```
query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A123456789%2C%22first_name%22%3A%22John%22%7D&auth_date=1234567890&hash=<hmac_sha256_hash>
```

### Алгоритм проверки (HMAC-SHA256)

1. Разобрать initData как URL-encoded параметры
2. Извлечь и удалить поле `hash`
3. Проверить свежесть `auth_date` (не старше 5 минут)
4. Отсортировать оставшиеся параметры по ключу
5. Сформировать `data_check_string` = `key=value\nkey=value\n...`
6. Вычислить `secret_key` = HMAC-SHA256(`"WebAppData"`, `BOT_TOKEN`)
7. Вычислить `hash` = HMAC-SHA256(`secret_key`, `data_check_string`)
8. Сравнить с полученным `hash`

### Роли

| Роль | Права |
|------|-------|
| `owner` | Полный доступ (чтение + запись + админ) |
| `member` | Чтение + запись |
| `viewer` | Только чтение (GET-запросы) |

### Dev-режим

При `SKIP_TELEGRAM_AUTH=true` аутентификация отключена, все запросы получают роль `owner`.

---

## System

### GET /api/health

Проверка доступности сервиса.

**Аутентификация:** не требуется

**Ответ:**
```json
{
  "status": "ok",
  "service": "ai_office"
}
```

### GET /api/status

Статус системы с информацией о текущем пользователе.

**Ответ:**
```json
{
  "status": "ok",
  "service": "ai_office",
  "agents_count": 8,
  "user_role": "owner"
}
```

---

## Agents

### GET /api/agents

Получить список всех агентов.

**Ответ:**
```json
[
  {
    "id": 1,
    "name": "alice",
    "role": "Personal Assistant / Product Manager",
    "status": "idle",
    "avatar_url": null
  },
  ...
]
```

### GET /api/agents/{agent_id}

Получить информацию об агенте по ID.

**Параметры пути:**
- `agent_id` (int) - ID агента

**Ответ:** объект агента (см. выше)

**Ошибки:**
- `404` - Агент не найден

### GET /api/agents/{agent_id}/activity

Лог активности конкретного агента.

**Query-параметры:**
- `limit` (int, 1-200, default: 20) - количество записей
- `offset` (int, >= 0, default: 0) - смещение

**Ответ:**
```json
{
  "items": [
    {
      "id": 1,
      "agent_id": 1,
      "agent_name": "alice",
      "action_type": "task_created",
      "action_description": "Создана задача: ...",
      "timestamp": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### GET /api/agents/{agent_id}/tasks

Задачи, назначенные агенту.

**Ответ:** массив объектов Task

---

## Tasks

### GET /api/tasks

Список задач с фильтрацией и пагинацией.

**Query-параметры:**
- `status` (string, optional) - фильтр по статусу (`open`, `in_progress`, `done`)
- `limit` (int, 1-200, default: 50) - количество записей
- `offset` (int, >= 0, default: 0) - смещение

**Ответ:**
```json
{
  "items": [
    {
      "id": 1,
      "description": "Рефакторинг модуля авторизации",
      "status": "open",
      "priority": "high",
      "executor_id": 2,
      "creator_type": "user",
      "creator_id": "api",
      "created_at": "2025-01-15T10:00:00Z"
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

### POST /api/tasks

Создать новую задачу.

**Тело запроса:**
```json
{
  "description": "Исправить баг в авторизации",
  "priority": "high",
  "executor_id": 2
}
```

**Ответ:** `201 Created` + объект Task

**WebSocket-событие:** `new_task`

### PATCH /api/tasks/{task_id}

Обновить задачу.

**Тело запроса:**
```json
{
  "status": "in_progress",
  "executor_id": 3
}
```

**Ответ:** обновленный объект Task

**WebSocket-событие:** `task_updated`

**Ошибки:**
- `404` - Задача не найдена

---

## Activity

### GET /api/activity

Лог последних действий всех агентов.

**Query-параметры:**
- `limit` (int, 1-200, default: 20)
- `offset` (int, >= 0, default: 0)

**Ответ:**
```json
{
  "items": [
    {
      "id": 1,
      "agent_id": 2,
      "agent_name": "sam",
      "action_type": "code_review",
      "action_description": "Ревью кода модуля auth",
      "timestamp": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

---

## Dashboard

### GET /api/dashboard

Агрегированные метрики для дашборда.

**Ответ:**
```json
{
  "tasks_today": 5,
  "tasks_week_history": [2, 3, 1, 5, 4, 3, 5],
  "cost_today": 0.045,
  "cost_week_history": [0.02, 0.03, 0.01, 0.05, 0.04, 0.03, 0.045],
  "avg_response_ms": 350,
  "response_time_history": [320, 340, 350, 360, 340, 350, 350],
  "response_time_estimated": true,
  "active_agents": 3,
  "hourly_activity": [0, 1, 2, 3, 1, 0, 0, 2, 5, 8, 7, 6, 4, 3, 2, 1, 0, 0, 1, 2, 3, 2, 1, 0]
}
```

---

## Plans

### GET /api/plans

Список планов с шагами.

**Ответ:**
```json
[
  {
    "id": 1,
    "title": "Рефакторинг авторизации",
    "status": "in_progress",
    "created_at": "2025-01-15T10:00:00Z",
    "steps": [
      {
        "id": 1,
        "description": "Анализ текущего кода",
        "status": "done",
        "order": 1
      },
      {
        "id": 2,
        "description": "Написание тестов",
        "status": "pending",
        "order": 2
      }
    ]
  }
]
```

### GET /api/plans/{plan_id}

Получить план по ID.

**Ошибки:**
- `404` - План не найден

---

## Delegations

### GET /api/delegations

Последние делегирования задач между агентами.

**Ответ:**
```json
[
  {
    "id": 1,
    "agent_id": 1,
    "agent_name": "alice",
    "action_type": "task_delegated",
    "action_description": "Делегировала задачу Sam'у: оптимизация запросов",
    "timestamp": "2025-01-15T10:30:00Z"
  }
]
```

### GET /api/delegations/{trace_id}/trace

Трассировка делегирования (цепочка сообщений между агентами).

**Ответ:**
```json
{
  "id": 1,
  "source_agent": "alice",
  "target_agent": "sam",
  "task_id": 5,
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "Нужно оптимизировать..."},
    {"role": "assistant", "content": "Выполнено..."}
  ],
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Ошибки:**
- `404` - Трассировка не найдена

---

## Usage

### GET /api/usage

Статистика использования токенов за сегодня.

**Ответ:**
```json
{
  "total_today": {
    "prompt_tokens": 15000,
    "completion_tokens": 5000,
    "total_cost": 0.045,
    "total_tokens": 20000
  },
  "per_agent": [
    {
      "agent_name": "alice",
      "prompt_tokens": 5000,
      "completion_tokens": 2000,
      "cost": 0.015,
      "calls": 10
    }
  ],
  "per_provider": [
    {
      "provider": "openai",
      "prompt_tokens": 12000,
      "completion_tokens": 4000,
      "cost": 0.035,
      "calls": 25
    }
  ],
  "daily_budget": 10.0,
  "budget_remaining": 9.955
}
```

---

## Metrics

### GET /api/metrics

Метрики в формате Prometheus text exposition.

**Аутентификация:** не требуется (для scraping)

**Content-Type:** `text/plain; version=0.0.4`

**Ответ:**
```
# HELP ai_office_requests_total Total HTTP requests
# TYPE ai_office_requests_total counter
ai_office_requests_total{method="GET",path="/api/agents",status="200"} 42
# HELP ai_office_memory_entries Agent memory entries
# TYPE ai_office_memory_entries gauge
ai_office_memory_entries{agent_name="alice"} 15
```

---

## Templates

### GET /api/templates

Список шаблонов задач.

**Ответ:**
```json
[
  {
    "id": 1,
    "name": "Code Review",
    "description_template": "Провести ревью кода: {описание}",
    "default_priority": "medium",
    "default_executor_name": "sam",
    "category": "dev",
    "icon": "code"
  }
]
```

### POST /api/tasks/from-template/{template_id}

Создать задачу из шаблона.

**Параметры пути:**
- `template_id` (int) - ID шаблона

**Ответ:** `201 Created` + объект Task

**WebSocket-событие:** `new_task`

**Ошибки:**
- `404` - Шаблон не найден

---

## Feedback

### POST /api/feedback

Создать запись обратной связи.

**Тело запроса:**
```json
{
  "user_telegram_id": 123456789,
  "agent_name": "alice",
  "message_id": "msg_001",
  "rating": 5,
  "is_positive": true,
  "comment": "Отличный ответ!"
}
```

**Ответ:** `201 Created` + объект Feedback

### GET /api/feedback/stats

Статистика обратной связи по агентам.

**Ответ:**
```json
[
  {
    "agent_name": "alice",
    "avg_rating": 4.5,
    "total_count": 25,
    "positive_percentage": 88.0
  }
]
```

---

## Plugins

### GET /api/plugins

Список загруженных плагинов.

**Ответ:**
```json
[
  {
    "name": "my_agent",
    "display_name": "My Agent",
    "role": "Custom Specialist",
    "tools": ["my_custom_tool"]
  }
]
```

### POST /api/plugins/reload

Перезагрузить все плагины.

**Доступ:** только `owner`

**Ответ:**
```json
{
  "status": "ok",
  "plugins": [...]
}
```

**Ошибки:**
- `403` - Только владелец может перезагружать плагины

---

## Admin

### GET /api/admin/settings

Список системных настроек.

**Доступ:** только `owner`

**Ответ:**
```json
[
  {
    "id": 1,
    "key": "daily_budget_usd",
    "value": "10.0"
  }
]
```

### PATCH /api/admin/settings

Обновить системные настройки.

**Доступ:** только `owner`

**Тело запроса:**
```json
{
  "daily_budget_usd": "15.0",
  "enable_proactive": "true"
}
```

**Ответ:**
```json
{
  "status": "ok",
  "updated": ["daily_budget_usd", "enable_proactive"]
}
```

### PATCH /api/admin/agents/{name}

Обновить системный промпт или статус агента.

**Доступ:** только `owner`

**Тело запроса:**
```json
{
  "system_prompt": "Новый промпт...",
  "enabled": true
}
```

**Ответ:**
```json
{
  "status": "ok",
  "agent": "alice",
  "agent_status": "idle"
}
```

### POST /api/admin/integrations/test

Тестировать подключение к внешней интеграции.

**Доступ:** только `owner`

**Тело запроса:**
```json
{
  "integration_type": "linear",
  "api_key": "lin_api_..."
}
```

**Ответ:**
```json
{
  "success": true,
  "message": "Linear подключен успешно"
}
```

Поддерживаемые типы: `linear`, `notion`

### GET /api/admin/workspaces

Список рабочих пространств (multi-tenant).

**Доступ:** только `owner`

**Ответ:**
```json
[
  {
    "id": 1,
    "name": "My Workspace",
    "owner_telegram_id": 123456789,
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

---

## WebSocket

### WS /api/ws

Real-time соединение для получения обновлений.

**Аутентификация:** не требуется (соединение открытое)

**Протокол:** после подключения сервер отправляет JSON-сообщения с событиями.

### События

| Событие | Описание | Данные |
|---------|----------|--------|
| `new_task` | Создана новая задача | `{id, description, status, priority}` |
| `task_updated` | Задача обновлена | `{id, status, description}` |
| `agent_status` | Изменился статус агента | `{agent_id, status}` |
| `stream_token` | Токен потокового ответа агента | `{agent_name, token, message_id}` |
| `stream_end` | Конец потокового ответа | `{agent_name, message_id}` |

### Формат сообщения

```json
{
  "event": "new_task",
  "data": {
    "id": 1,
    "description": "Новая задача",
    "status": "open",
    "priority": "high"
  }
}
```

### Пример подключения (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  switch (message.event) {
    case 'new_task':
      console.log('New task:', message.data);
      break;
    case 'stream_token':
      // Append token to agent's response
      appendToken(message.data.agent_name, message.data.token);
      break;
    case 'stream_end':
      // Mark response as complete
      finishStream(message.data.agent_name);
      break;
  }
};
```

---

## Коды ответов

| Код | Описание |
|-----|----------|
| `200` | Успешный запрос |
| `201` | Ресурс создан |
| `401` | Не авторизован (отсутствует или невалидный initData) |
| `403` | Недостаточно прав (viewer пытается записать, или не owner для admin) |
| `404` | Ресурс не найден |
| `429` | Rate limit превышен |
| `500` | Внутренняя ошибка сервера |

## Пагинация

Эндпоинты с пагинацией возвращают обертку:

```json
{
  "items": [...],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

Параметры:
- `limit` - количество записей на страницу (1-200)
- `offset` - смещение от начала
