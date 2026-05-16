# Zenith-Control Ultimate: deploy-kit

Набор артефактов для развёртывания funding-арбитражного бота на VPS.
Поддерживаются два пути: нативный **systemd** под Ubuntu 22/24/26 и Debian 12/13,
либо **Docker Compose** на любом Linux с установленным Docker.

## Возможности

- **8 бирж**: Bybit, OKX, Binance, Gate.io, Bitget, MEXC, HTX, BingX
- **20 символов** в скане фандинга (BTCUSDT … JUPUSDT)
- **До 3 одновременных арб-пар** (управляется `ARB_MAX_POSITIONS`)
- Панель управления через Telegram-бота: позиции, биржи, kill-switch

## Структура deploy/

| Файл | Назначение |
|---|---|
| `install.sh` | Идемпотентный bash-установщик (systemd) |
| `zenith.service` | Unit-файл systemd (автозапуск, `User=zenith`) |
| `Dockerfile` | Образ `python:3.11-slim` с пользователем `zenith` |
| `docker-compose.yml` | Сервис `zenith` + volume для SQLite |
| `.env.example` | Шаблон переменных окружения для всех 8 бирж |

## Быстрый старт: Ubuntu VPS (рекомендовано)

```bash
# 1. Подключиться по SSH
ssh root@<ваш-IP>

# 2. Скопировать папку zenith-bot/ на сервер через scp или rsync
scp -r zenith-bot/ root@<ваш-IP>:/opt/zenith

# 3. Установить зависимости
apt-get update && apt-get install -y python3 python3-venv
python3 -m venv /opt/zenith/.venv
/opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt

# 4. Заполнить .env (все ключи нужных бирж + Telegram)
cp /opt/zenith/deploy/.env.example /opt/zenith/.env
nano /opt/zenith/.env

# 5. Установить systemd-сервис
cp /opt/zenith/deploy/zenith.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now zenith
journalctl -u zenith -f
```

## Обязательные переменные .env

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

IS_TESTNET=true          # true = testnet (безопасно), false = mainnet
ARB_EXECUTOR_ENABLED=0   # 0 = только сканирование; 1 = авто-арбитраж

# Хотя бы одна пара ключей для биржи:
BYBIT_API_KEY=...
BYBIT_API_SECRET=...

# Остальные биржи — по желанию (полный список в .env.example)
TRADES_DB_PATH=/opt/zenith/data/trades.db
```

## Мульти-позиция (ARB_MAX_POSITIONS)

По умолчанию бот одновременно держит до **3** арб-пар на разных символах.
Чтобы изменить лимит, добавьте в `.env` или установите в `config.py`:

```env
ARB_MAX_POSITIONS=2   # меньше капитала
ARB_MAX_POSITIONS=5   # больше пар (нужно больше свободной маржи)
```

При `N` парах по `ARB_NOTIONAL_USDT=200` нужно ~200 USDT margin
**на каждой задействованной бирже**.

## Включение авто-арбитража

```bash
# Убедитесь: бот ≥24ч работает без ошибок, Telegram принимает команды.
sed -i 's/ARB_EXECUTOR_ENABLED=0/ARB_EXECUTOR_ENABLED=1/' /opt/zenith/.env
systemctl restart zenith
```

## Управление через systemd

```bash
systemctl status zenith
journalctl -u zenith -f          # логи в реальном времени
journalctl -u zenith -n 200      # последние 200 строк
systemctl restart zenith
systemctl stop zenith
```

## Docker Compose

```bash
cp deploy/.env.example .env && nano .env
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml logs -f
docker compose -f deploy/docker-compose.yml restart
```

## Обновление

```bash
# Скопировать новые файлы на сервер и перезапустить:
rsync -av --exclude='*.pyc' --exclude='trades.db' --exclude='.env' \
      zenith-bot/ root@<IP>:/opt/zenith/
systemctl restart zenith
```

## Откат

Сохраните базу перед откатом:
```bash
cp /opt/zenith/data/trades.db /opt/zenith/data/trades.db.bak
```
Затем замените файлы предыдущей версией и перезапустите.

## Частые проблемы

**HTTP 409 от Telegram** — два инстанса бота с одним токеном. Остановите лишний.

**`Отсутствуют обязательные переменные`** — `.env` не заполнен или не виден systemd.
Проверьте: `systemctl show zenith -p EnvironmentFile`

**Нет сделок за сутки** — нормально. Арбитраж открывается только когда
`net_edge_apr ≥ ARB_OPEN_MIN_NET_APR` (по умолчанию 20% годовых).

**`unable to open database file`** — каталог для `TRADES_DB_PATH` не создан.
```bash
mkdir -p /opt/zenith/data && chown zenith:zenith /opt/zenith/data
```

**Биржа не сканируется** — API-ключи не заданы или неверны. Бот логирует
ошибку аутентификации с тегом `[БИРЖА]` и пропускает её; остальные работают.
