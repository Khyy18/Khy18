#!/usr/bin/env bash
# =============================================================================
# Smoke-тест AI Office (локальный запуск)
# Проверяет работоспособность API после установки зависимостей и миграций.
# =============================================================================

set -euo pipefail

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # Без цвета

# Счётчики
PASSED=0
FAILED=0
TOTAL=0

# Базовый URL
BASE_URL="http://localhost:8000"

# PID фонового сервера
SERVER_PID=""

# Очистка при завершении
cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo -e "\n${YELLOW}Останавливаем сервер (PID: $SERVER_PID)...${NC}"
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Функция проверки
check() {
    local description="$1"
    local result="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$result" -eq 0 ]; then
        echo -e "  ${GREEN}[PASS]${NC} $description"
        PASSED=$((PASSED + 1))
    else
        echo -e "  ${RED}[FAIL]${NC} $description"
        FAILED=$((FAILED + 1))
    fi
}

# Функция проверки GET-эндпоинта (HTTP 200 + валидный JSON)
check_endpoint() {
    local endpoint="$1"
    local description="$2"
    local response
    local http_code

    http_code=$(curl -s -o /tmp/smoke_response.json -w "%{http_code}" "$BASE_URL$endpoint")
    if [ "$http_code" = "200" ] && python3 -c "import json; json.load(open('/tmp/smoke_response.json'))" 2>/dev/null; then
        check "$description" 0
    else
        check "$description" 1
    fi
}

echo "============================================="
echo "  AI Office - Smoke Test (локальный)"
echo "============================================="
echo ""

# --- 1. Проверка версии Python ---
echo "1. Проверка Python >= 3.11..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 11 ]; then
    check "Python $PYTHON_VERSION >= 3.11" 0
else
    check "Python $PYTHON_VERSION >= 3.11" 1
    echo -e "${RED}Требуется Python 3.11+. Прерываем.${NC}"
    exit 1
fi

# --- 2. Проверка переменных окружения ---
echo ""
echo "2. Проверка переменных окружения..."
if [ -n "${OPENAI_API_KEY:-}" ]; then
    check "OPENAI_API_KEY установлен" 0
else
    echo -e "  ${YELLOW}[WARN]${NC} OPENAI_API_KEY не установлен (LLM-вызовы могут не работать)"
fi
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    check "TELEGRAM_BOT_TOKEN установлен" 0
else
    echo -e "  ${YELLOW}[WARN]${NC} TELEGRAM_BOT_TOKEN не установлен (Telegram-бот не запустится)"
fi

# --- 3. Установка зависимостей ---
echo ""
echo "3. Установка зависимостей (если требуется)..."
if python3 -c "import fastapi, sqlalchemy, pydantic_settings" 2>/dev/null; then
    echo -e "  ${GREEN}[OK]${NC} Зависимости уже установлены"
else
    echo "  Устанавливаем requirements.txt..."
    pip install -r requirements.txt -q
    check "pip install -r requirements.txt" $?
fi

# --- 4. Запуск миграций ---
echo ""
echo "4. Запуск миграций (alembic upgrade head)..."
if [ -f "alembic.ini" ]; then
    alembic upgrade head 2>/dev/null
    check "alembic upgrade head" $?
else
    echo -e "  ${YELLOW}[WARN]${NC} alembic.ini не найден, пропускаем миграции"
fi

# --- 5. Запуск FastAPI сервера ---
echo ""
echo "5. Запуск FastAPI сервера..."
python3 -m uvicorn ai_office.api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
echo "  Сервер запущен (PID: $SERVER_PID)"

# --- 6. Ожидание health-check ---
echo ""
echo "6. Ожидание health-check..."
RETRIES=5
HEALTHY=false
for i in $(seq 1 $RETRIES); do
    sleep 2
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        HEALTHY=true
        break
    fi
    echo "  Попытка $i/$RETRIES - код: $HTTP_CODE"
done
if [ "$HEALTHY" = true ]; then
    check "Health-check /api/health" 0
else
    check "Health-check /api/health" 1
    echo -e "${RED}Сервер не ответил. Прерываем.${NC}"
    exit 1
fi

# --- 7. Проверка GET-эндпоинтов ---
echo ""
echo "7. Проверка GET-эндпоинтов..."
check_endpoint "/api/agents" "GET /api/agents (200 + JSON)"
check_endpoint "/api/tasks" "GET /api/tasks (200 + JSON)"
check_endpoint "/api/activity" "GET /api/activity (200 + JSON)"
check_endpoint "/api/dashboard" "GET /api/dashboard (200 + JSON)"
check_endpoint "/api/plugins" "GET /api/plugins (200 + JSON)"

# --- 8. Создание тестовой задачи ---
echo ""
echo "8. Создание тестовой задачи (POST /api/tasks)..."
CREATE_CODE=$(curl -s -o /tmp/smoke_create.json -w "%{http_code}" \
    -X POST "$BASE_URL/api/tasks" \
    -H "Content-Type: application/json" \
    -d '{"description": "Smoke test task", "priority": "low"}')

if [ "$CREATE_CODE" = "200" ] || [ "$CREATE_CODE" = "201" ]; then
    check "POST /api/tasks - создание задачи" 0
else
    check "POST /api/tasks - создание задачи (код: $CREATE_CODE)" 1
fi

# --- 9. Проверка наличия задачи ---
echo ""
echo "9. Проверка наличия задачи в списке..."
sleep 1
TASKS_RESPONSE=$(curl -s "$BASE_URL/api/tasks")
if echo "$TASKS_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tasks = data if isinstance(data, list) else data.get('tasks', data.get('items', []))
found = any('Smoke test task' in str(t) for t in tasks)
sys.exit(0 if found else 1)
" 2>/dev/null; then
    check "Задача 'Smoke test task' найдена в GET /api/tasks" 0
else
    check "Задача 'Smoke test task' найдена в GET /api/tasks" 1
fi

# --- 10. Остановка сервера (cleanup сделает trap) ---
echo ""
echo "10. Остановка сервера..."
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""
echo -e "  ${GREEN}[OK]${NC} Сервер остановлен"

# --- 11. Итоги ---
echo ""
echo "============================================="
if [ "$FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}РЕЗУЛЬТАТ: $PASSED/$TOTAL проверок пройдено${NC}"
else
    echo -e "  ${RED}РЕЗУЛЬТАТ: $PASSED/$TOTAL проверок пройдено ($FAILED ошибок)${NC}"
fi
echo "============================================="

exit "$FAILED"
