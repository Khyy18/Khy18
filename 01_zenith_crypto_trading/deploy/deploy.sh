#!/bin/bash
set -euo pipefail

# Blue-green deployment script for Zenith Control
# Использование: ./deploy.sh [--rollback]

COMPOSE_FILE="docker-compose.prod.yml"
UPSTREAM_CONF="active_upstream.conf"
MAX_RETRIES=30
RETRY_INTERVAL=1

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Определяем текущий активный цвет по порту в active_upstream.conf
get_current_color() {
    if grep -q "8081" "$UPSTREAM_CONF"; then
        echo "blue"
    elif grep -q "8082" "$UPSTREAM_CONF"; then
        echo "green"
    else
        echo "blue"
    fi
}

# Получаем порт для указанного цвета
get_port() {
    local color="$1"
    if [ "$color" = "blue" ]; then
        echo "8081"
    else
        echo "8082"
    fi
}

# Получаем противоположный цвет
get_opposite_color() {
    local color="$1"
    if [ "$color" = "blue" ]; then
        echo "green"
    else
        echo "blue"
    fi
}

# Переключаем upstream на указанный цвет
switch_upstream() {
    local target_color="$1"
    local target_port
    target_port=$(get_port "$target_color")

    cat > "$UPSTREAM_CONF" <<EOF
upstream active {
    server 127.0.0.1:${target_port};
}
EOF
    log_info "Upstream переключен на ${target_color} (порт ${target_port})"
}

# Перезагрузка nginx
reload_nginx() {
    docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload
    log_info "Nginx перезагружен"
}

# Проверка здоровья сервиса
health_check() {
    local port="$1"
    local retries=0

    log_info "Проверка здоровья на порту ${port}..."

    while [ $retries -lt $MAX_RETRIES ]; do
        if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
            log_info "Сервис на порту ${port} здоров"
            return 0
        fi
        retries=$((retries + 1))
        log_warn "Попытка ${retries}/${MAX_RETRIES}..."
        sleep $RETRY_INTERVAL
    done

    log_error "Сервис на порту ${port} не отвечает после ${MAX_RETRIES} попыток"
    return 1
}

# Откат к предыдущему цвету
rollback() {
    local current_color
    current_color=$(get_current_color)
    local target_color
    target_color=$(get_opposite_color "$current_color")

    log_info "Откат: переключение с ${current_color} на ${target_color}"
    switch_upstream "$target_color"
    reload_nginx
    log_info "Откат завершен. Активный сервис: ${target_color}"
}

# Основной процесс деплоя
deploy() {
    local current_color
    current_color=$(get_current_color)
    local target_color
    target_color=$(get_opposite_color "$current_color")
    local target_port
    target_port=$(get_port "$target_color")
    local target_service="zenith-${target_color}"

    log_info "Текущий активный: ${current_color}"
    log_info "Целевой сервис: ${target_service} (порт ${target_port})"

    # Сборка целевого сервиса
    log_info "Сборка ${target_service}..."
    docker compose -f "$COMPOSE_FILE" build "$target_service"

    # Запуск целевого сервиса
    log_info "Запуск ${target_service}..."
    docker compose -f "$COMPOSE_FILE" up -d "$target_service"

    # Проверка здоровья
    if health_check "$target_port"; then
        # Переключение трафика
        switch_upstream "$target_color"
        reload_nginx

        # Остановка старого сервиса
        local old_service="zenith-${current_color}"
        log_info "Остановка ${old_service}..."
        docker compose -f "$COMPOSE_FILE" stop "$old_service"

        log_info "Деплой завершен успешно!"
        log_info "Активный сервис: ${target_color} (порт ${target_port})"
    else
        # Ошибка - останавливаем целевой сервис
        log_error "Деплой не удался - сервис не прошел проверку здоровья"
        log_error "Останавливаем ${target_service}..."
        docker compose -f "$COMPOSE_FILE" stop "$target_service"
        log_error "Активный сервис остался: ${current_color}"
        exit 1
    fi
}

# Парсинг аргументов
if [ "${1:-}" = "--rollback" ]; then
    rollback
else
    deploy
fi
