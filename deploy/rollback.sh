#!/bin/bash
set -euo pipefail

# Скрипт отката для Zenith Control
# Переключает active_upstream.conf на противоположный цвет и перезагружает nginx

COMPOSE_FILE="docker-compose.prod.yml"
UPSTREAM_CONF="active_upstream.conf"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Определяем текущий активный цвет
if grep -q "8081" "$UPSTREAM_CONF"; then
    current_color="blue"
    target_color="green"
    target_port="8082"
elif grep -q "8082" "$UPSTREAM_CONF"; then
    current_color="green"
    target_color="blue"
    target_port="8081"
else
    log_error "Не удалось определить текущий активный сервис"
    exit 1
fi

log_info "Текущий активный: ${current_color}"
log_info "Переключение на: ${target_color} (порт ${target_port})"

# Обновляем active_upstream.conf
cat > "$UPSTREAM_CONF" <<EOF
upstream active {
    server 127.0.0.1:${target_port};
}
EOF

# Перезагружаем nginx
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload

log_info "Откат завершен. Активный сервис: ${target_color}"
