#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}"
echo "============================================="
echo "  Бухгалтер детского сада - Установка"
echo "============================================="
echo -e "${NC}"
echo ""

# Check if .env already exists
if [ -f .env ]; then
    echo -e "${YELLOW}Файл .env уже существует. Перезаписать? [y/N]${NC}"
    read -p "> " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Установка отменена. Существующий .env сохранён.${NC}"
        exit 0
    fi
    echo ""
fi

# --- BOT_TOKEN ---
echo -e "${YELLOW}1. BOT_TOKEN${NC}"
echo "   Получите токен у @BotFather в Telegram (команда /newbot)"
while true; do
    read -p "   Введите BOT_TOKEN: " BOT_TOKEN
    if [ -n "$BOT_TOKEN" ]; then
        break
    fi
    echo -e "   ${RED}BOT_TOKEN не может быть пустым. Попробуйте снова.${NC}"
done
echo ""

# --- GROQ_API_KEY ---
echo -e "${YELLOW}2. GROQ_API_KEY${NC}"
echo "   Получите бесплатный ключ на https://console.groq.com/keys"
while true; do
    read -p "   Введите GROQ_API_KEY: " GROQ_API_KEY
    if [ -n "$GROQ_API_KEY" ]; then
        break
    fi
    echo -e "   ${RED}GROQ_API_KEY не может быть пустым. Попробуйте снова.${NC}"
done
echo ""

# --- ENCRYPTION_KEY ---
echo -e "${YELLOW}3. ENCRYPTION_KEY${NC}"
echo "   Ключ шифрования данных (32 байта hex)."
echo "   Нажмите Enter для автогенерации."
read -p "   Введите ENCRYPTION_KEY (или Enter): " ENCRYPTION_KEY
if [ -z "$ENCRYPTION_KEY" ]; then
    ENCRYPTION_KEY=$(openssl rand -hex 32)
    echo -e "   ${GREEN}Сгенерирован: ${ENCRYPTION_KEY}${NC}"
fi
echo ""

# --- SECRET_KEY ---
echo -e "${YELLOW}4. SECRET_KEY${NC}"
echo "   Секретный ключ приложения (для JWT и сессий)."
echo "   Нажмите Enter для автогенерации."
read -p "   Введите SECRET_KEY (или Enter): " SECRET_KEY
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    echo -e "   ${GREEN}Сгенерирован: ${SECRET_KEY}${NC}"
fi
echo ""

# --- ADMIN_CHAT_ID ---
echo -e "${YELLOW}5. ADMIN_CHAT_ID${NC}"
echo "   Узнайте свой chat_id у бота @userinfobot в Telegram"
read -p "   Введите ADMIN_CHAT_ID: " ADMIN_CHAT_ID
echo ""

# --- Write .env ---
echo -e "${BLUE}Записываю .env файл...${NC}"
cat > .env << EOF
# Автоматически сгенерировано setup.sh
BOT_TOKEN=${BOT_TOKEN}
GROQ_API_KEY=${GROQ_API_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
SECRET_KEY=${SECRET_KEY}
ADMIN_CHAT_ID=${ADMIN_CHAT_ID}
BOT_ADMIN_IDS=${ADMIN_CHAT_ID}

# База данных (Docker Compose)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/kindergarten

# Sentry (опционально)
SENTRY_DSN=

# WebApp URL (опционально)
WEBAPP_URL=
EOF

echo -e "${GREEN}Файл .env создан успешно!${NC}"
chmod 600 .env
echo ""

# --- Docker Compose ---
echo -e "${BLUE}Запускаю Docker Compose...${NC}"
if command -v docker compose &> /dev/null; then
    docker compose up -d
elif command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    echo -e "${RED}Docker Compose не найден. Установите Docker и Docker Compose.${NC}"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Установка завершена!${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "  Backend API:  ${BLUE}http://localhost:8000${NC}"
echo -e "  Бот:          ${GREEN}запущен${NC}"
echo -e "  PostgreSQL:   ${GREEN}localhost:5432${NC}"
echo ""
echo -e "  Для просмотра логов: ${YELLOW}docker compose logs -f${NC}"
echo -e "  Для остановки:       ${YELLOW}docker compose down${NC}"
echo ""
