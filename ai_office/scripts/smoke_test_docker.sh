#!/usr/bin/env bash
# =============================================================================
# Smoke-тест AI Office (Docker Compose)
# Проверяет работоспособность API через nginx (порт 80) после сборки контейнеров.
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

# Базовый URL (через nginx)
BASE_URL="http://localhost:80"

# Очистка при завершении
cleanup() {
    echo -e "\n${YELLOW}Останавливаем контейнеры...${NC}"
    docker compose -f deploy/docker-compose.yml down 2>/dev/null || true
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
    local http_code

    http_code=$(curl -s -o /tmp/smoke_docker_response.json -w "%{http_code}" "$BASE_URL$endpoint")
    if [ "$http_code" = "200" ] && python3 -c "import json; json.load(open('/tmp/smoke_docker_response.json'))" 2>/dev/null; then
        check "$description" 0
    else
        check "$description" 1
    fi
}

echo "============================================="
echo "  AI Office - Smoke Test (Docker Compose)"
echo "============================================="
echo ""

# --- 1. Запуск контейнеров ---
echo "1. Запуск контейнеров (docker compose up)..."
docker compose -f deploy/docker-compose.yml up -d --build
if [ $? -eq 0 ]; then
    check "docker compose up -d --build" 0
else
    check "docker compose up -d --build" 1
    echo -e "${RED}Не удалось запустить контейнеры. Прерываем.${NC}"
    exit 1
fi

# --- 2. Ожидание готовности сервисов ---
echo ""
echo "2. Ожидание готовности сервисов..."
RETRIES=10
ALL_HEALTHY=false
for i in $(seq 1 $RETRIES); do
    sleep 3
    # Проверяем что все контейнеры running
    RUNNING=$(docker compose -f deploy/docker-compose.yml ps --status running -q 2>/dev/null | wc -l)
    TOTAL_SERVICES=$(docker compose -f deploy/docker-compose.yml ps -q 2>/dev/null | wc -l)
    if [ "$RUNNING" -gt 0 ] && [ "$RUNNING" -eq "$TOTAL_SERVICES" ]; then
        ALL_HEALTHY=true
        break
    fi
    echo "  Попытка $i/$RETRIES - запущено: $RUNNING/$TOTAL_SERVICES"
done
if [ "$ALL_HEALTHY" = true ]; then
    check "Все сервисы запущены" 0
else
    check "Все сервисы запущены" 1
    echo -e "${YELLOW}Некоторые сервисы не запустились, продолжаем проверку...${NC}"
fi

# --- 3. Ожидание health-check через nginx ---
echo ""
echo "3. Ожидание health-check (через nginx, порт 80)..."
RETRIES=10
HEALTHY=false
for i in $(seq 1 $RETRIES); do
    sleep 3
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        HEALTHY=true
        break
    fi
    echo "  Попытка $i/$RETRIES - код: $HTTP_CODE"
done
if [ "$HEALTHY" = true ]; then
    check "Health-check /api/health (nginx)" 0
else
    check "Health-check /api/health (nginx)" 1
    echo -e "${RED}Сервер не ответил через nginx. Прерываем.${NC}"
    exit 1
fi

# --- 4. Проверка GET-эндпоинтов ---
echo ""
echo "4. Проверка GET-эндпоинтов..."
check_endpoint "/api/agents" "GET /api/agents (200 + JSON)"
check_endpoint "/api/tasks" "GET /api/tasks (200 + JSON)"
check_endpoint "/api/activity" "GET /api/activity (200 + JSON)"
check_endpoint "/api/dashboard" "GET /api/dashboard (200 + JSON)"
check_endpoint "/api/plugins" "GET /api/plugins (200 + JSON)"

# --- 5. Создание тестовой задачи ---
echo ""
echo "5. Создание тестовой задачи (POST /api/tasks)..."
CREATE_CODE=$(curl -s -o /tmp/smoke_docker_create.json -w "%{http_code}" \
    -X POST "$BASE_URL/api/tasks" \
    -H "Content-Type: application/json" \
    -d '{"description": "Smoke test task", "priority": "low"}')

if [ "$CREATE_CODE" = "200" ] || [ "$CREATE_CODE" = "201" ]; then
    check "POST /api/tasks - создание задачи" 0
else
    check "POST /api/tasks - создание задачи (код: $CREATE_CODE)" 1
fi

# --- 6. Проверка наличия задачи ---
echo ""
echo "6. Проверка наличия задачи в списке..."
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

# --- 7. Остановка контейнеров (cleanup сделает trap) ---
echo ""
echo "7. Остановка контейнеров..."
docker compose -f deploy/docker-compose.yml down
echo -e "  ${GREEN}[OK]${NC} Контейнеры остановлены"

# Отключаем trap чтобы не дублировать cleanup
trap - EXIT

# --- 8. Итоги ---
echo ""
echo "============================================="
if [ "$FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}РЕЗУЛЬТАТ: $PASSED/$TOTAL проверок пройдено${NC}"
else
    echo -e "  ${RED}РЕЗУЛЬТАТ: $PASSED/$TOTAL проверок пройдено ($FAILED ошибок)${NC}"
fi
echo "============================================="

exit "$FAILED"
