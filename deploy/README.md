# Zenith-Control Ultimate: deploy-kit

Набор артефактов для развёртывания торгового бота v2 на VPS. Поддерживаются
два пути: нативный systemd-сервис под Ubuntu 22.04 / Debian 12 и запуск
через Docker Compose на любом современном Linux с установленными
`docker` и `docker compose`.

## Обзор

Структура директории `deploy/`:

- `install.sh` - идемпотентный bash-установщик под systemd.
- `zenith.service` - unit-файл systemd (`User=zenith`, автозапуск, Restart=always).
- `Dockerfile` - образ на базе `python:3.11-slim` с системным пользователем `zenith`.
- `docker-compose.yml` - сервис `zenith` с монтированием `trades.db` и `env_file`.
- `README.md` - этот файл.

Бот ставится в `/opt/zenith`, работает от имени пользователя `zenith`,
читает секреты из `/opt/zenith/.env` и пишет журнал в `journalctl -u zenith`
(или в stdout контейнера при Docker-пути).

## Быстрая установка через systemd

Рекомендованный способ для production-VPS. Работает на Ubuntu 22.04 и
Debian 12. Запускать надо под root (sudo).

```bash
curl -fsSL https://raw.githubusercontent.com/<OWNER>/<REPO>/feat/zenith-control-ultimate/deploy/install.sh | sudo bash
```

Замените `<OWNER>/<REPO>` на реальный форк (например, `your-user/Khy18`).
Путь `feat/zenith-control-ultimate` указывает на ветку с v2. После выхода
v2 в main замените на `main`.

Скрипт идемпотентен: повторный запуск подтянет последние коммиты и
перегенерирует venv, но не перезапишет уже заполненный `.env`.

## Ручная установка через systemd

Полезно, если скрипт нельзя запустить одной командой.

```bash
# 1. Базовые пакеты (Ubuntu 22.04 требует deadsnakes PPA для python3.11).
sudo apt-get update
sudo apt-get install -y git curl ca-certificates software-properties-common
# Ubuntu 22.04:
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv
# Debian 12 (python3.11 в main):
# sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# 2. Системный пользователь и каталог.
sudo useradd --system --create-home --home-dir /home/zenith --shell /bin/bash zenith
sudo install -d -o zenith -g zenith /opt/zenith

# 3. Код.
sudo -u zenith git clone https://github.com/Khy18/Khy18.git /opt/zenith

# 4. venv и зависимости.
sudo -u zenith python3.11 -m venv /opt/zenith/.venv
sudo -u zenith /opt/zenith/.venv/bin/pip install --upgrade pip
sudo -u zenith /opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt

# 5. .env (заполните реальными ключами).
sudo -u zenith cp /opt/zenith/.env.example /opt/zenith/.env
sudo -u zenith nano /opt/zenith/.env

# 6. systemd unit.
sudo install -m 644 /opt/zenith/deploy/zenith.service /etc/systemd/system/zenith.service
sudo systemctl daemon-reload
sudo systemctl enable --now zenith.service
```

## Запуск через Docker Compose

Простая альтернатива, если systemd недоступен или хочется изоляции.

```bash
# 1. Клонируем и заполняем .env.
git clone https://github.com/Khy18/Khy18.git
cd Khy18
cp .env.example .env
nano .env

# 2. Собираем образ и поднимаем сервис.
docker compose -f deploy/docker-compose.yml up -d --build
```

`docker-compose.yml` монтирует `../trades.db` наружу контейнера, чтобы
SQLite-журнал переживал пересборки. Файл `../.env` читается через
`env_file` и не попадает в образ.

## Мониторинг

Systemd-путь:

```bash
sudo systemctl status zenith
sudo journalctl -u zenith -f
```

Docker-путь:

```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f
```

Русскоязычные логи бота снабжены тегами `[MAIN]`, `[LOOP]`, `[KILL]`,
`[TG]`, `[AI]`, `[API]`, `[MEMORY]`, `[NEWS]` - удобно грепать по ним.

## Обновление

Systemd:

```bash
sudo -u zenith git -C /opt/zenith pull --ff-only
sudo -u zenith /opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt
sudo systemctl restart zenith
```

Docker:

```bash
git pull --ff-only
docker compose -f deploy/docker-compose.yml up -d --build
```

## Откат

Systemd-путь:

```bash
# Откатиться на заведомо рабочий коммит:
sudo -u zenith git -C /opt/zenith log --oneline -20
sudo -u zenith git -C /opt/zenith reset --hard <commit-sha>
sudo systemctl restart zenith
```

Docker-путь:

```bash
git reset --hard <commit-sha>
docker compose -f deploy/docker-compose.yml up -d --build
```

Если вы подозреваете повреждение базы сделок, сохраните копию
`trades.db` до отката (`cp trades.db trades.db.bak`). Таблицы создаются
идемпотентно, бот не удаляет существующие записи.
