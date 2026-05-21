# Деплой Price Monitor

## Требования

- VPS: 2 CPU, 4GB RAM, 40GB SSD (рекомендация: Timeweb Cloud, ~1000 р/мес)
- Домен (для SSL и Telegram Mini App)
- Docker + Docker Compose

## 1. Подготовка сервера

```bash
# Обновить систему
apt update && apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com | sh

# Установить Docker Compose
apt install docker-compose-plugin -y

# Создать директорию проекта
mkdir -p /opt/price-monitor
cd /opt/price-monitor
```

## 2. Клонирование и настройка

```bash
# Клонировать репозиторий
git clone https://github.com/YOUR_USER/YOUR_REPO.git .

# Перейти в проект
cd price_monitor

# Создать .env
cp .env.example .env
nano .env  # заполнить все переменные
```

## 3. SSL-сертификат (Let's Encrypt)

```bash
# Установить certbot
apt install certbot -y

# Получить сертификат
certbot certonly --standalone -d your-domain.com

# Сертификаты будут в:
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem
```

## 4. Запуск

```bash
# Поднять инфраструктуру + все сервисы
cd infra
docker-compose up -d

# Проверить статус
docker-compose ps

# Логи
docker-compose logs -f backend
docker-compose logs -f bot
```

## 5. Настройка Telegram

1. Открыть @BotFather
2. `/mybots` -> выбрать бота -> Bot Settings -> Menu Button
3. Указать URL: `https://your-domain.com`
4. Готово - Mini App привязана к боту

## 6. Проверка

```bash
# API работает
curl https://your-domain.com/health

# WebSocket
wscat -c "wss://your-domain.com/ws/prices?token=YOUR_JWT"
```

## 7. Мониторинг

### Sentry
1. Зарегистрироваться на sentry.io
2. Создать проект (Python -> FastAPI)
3. Скопировать DSN в .env (`SENTRY_DSN=...`)

### Логи
```bash
# Все логи
docker-compose logs -f

# Только бэкенд
docker-compose logs -f backend

# Только бот
docker-compose logs -f bot
```

## 8. Бэкапы

```bash
# Добавить в crontab
crontab -e

# Бэкап PostgreSQL каждый день в 3:00
0 3 * * * docker exec postgres pg_dump -U price_monitor price_monitor > /opt/backups/db_$(date +\%Y\%m\%d).sql

# Хранить последние 7 дней
0 4 * * * find /opt/backups -name "db_*.sql" -mtime +7 -delete
```

## 9. Обновление

```bash
cd /opt/price-monitor/price_monitor

# Забрать изменения
git pull origin main

# Пересобрать и перезапустить
cd infra
docker-compose up -d --build
```

## Checklist перед запуском

- [ ] Заполнен .env (все токены)
- [ ] SSL-сертификат получен
- [ ] PostgreSQL + Redis запущены
- [ ] API отвечает на /health
- [ ] Telegram Mini App открывается
- [ ] Бот отвечает на /start
- [ ] Парсеры получают данные (проверить через /admin/parser-status)
- [ ] ЮKassa webhook доступен извне
- [ ] Sentry получает события
- [ ] Бэкапы настроены
