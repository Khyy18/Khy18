# Zenith-Control Ultimate: deploy-kit

Набор артефактов для развёртывания торгового бота v2 на VPS. Поддерживаются
два пути: нативный systemd-сервис под Ubuntu 22.04/24.04/26.04 и Debian 12/13,
либо запуск через Docker Compose на любом современном Linux с установленными
`docker` и `docker compose`.

## Обзор

Структура директории `deploy/`:

- `install.sh` - идемпотентный bash-установщик под systemd.
- `zenith.service` - unit-файл systemd (`User=zenith`, автозапуск, Restart=always).
- `Dockerfile` - образ на базе `python:3.11-slim` с системным пользователем `zenith`.
- `docker-compose.yml` - сервис `zenith` с монтированием `trades.db` и `env_file`.
- `README.md` - этот файл.

Бот ставится в `/opt/zenith`, работает от имени пользователя `zenith`,
читает секреты из `/opt/zenith/.env`, хранит SQLite в `/opt/zenith/data/trades.db`
(переживает `git pull`/переустановки) и пишет журнал в `journalctl -u zenith`.

## Быстрый старт на Ubuntu VPS (рекомендовано)

Проверено на Ubuntu 22.04 / 24.04 / 26.04 и Debian 12 / 13.
Перед началом убедитесь что на этом `TELEGRAM_TOKEN` нигде не запущен
второй бот (локально, в старой сессии, на другом хостинге). Telegram
отдаёт `getUpdates` только одному клиенту - иначе будет HTTP 409 и
потеря команд из чата.

```bash
# 1. Подключиться к серверу по SSH (под root или через sudo su).
#    IP, логин и пароль - из письма от хостинг-провайдера.
ssh root@<ваш-IP>

# 2. Запустить установщик одной командой.
curl -fsSL https://raw.githubusercontent.com/Khyy18/Khy18/feat/zenith-control-ultimate/deploy/install.sh | sudo bash

# 3. Заполнить .env реальными ключами.
sudo -u zenith cp /opt/zenith/.env.example /opt/zenith/.env
sudo -u zenith nano /opt/zenith/.env
```

В `.env` обязательно (для EXCHANGE=okx):

```env
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
GROQ_API_KEY=...
NEWS_API_KEY=...

# Путь к persistent SQLite (каталог создаётся install.sh).
TRADES_DB_PATH=/opt/zenith/data/trades.db

# Paper-trading: сигналы считаются, ордера НЕ отправляются.
# Держите true хотя бы 24 часа для наблюдения.
DRY_RUN=true
```

```bash
# 4. Запустить сервис.
sudo systemctl start zenith

# 5. Смотреть журнал в реальном времени (Ctrl+C для выхода).
sudo journalctl -u zenith -f
```

В норме за первую минуту в логе появятся:

```
[MEMORY] База данных trades.db инициализирована: /opt/zenith/data/trades.db
[MAIN] Zenith-Control Ultimate v2 запущен
[MAIN] Успех авторизации на OKX (TESTNET). Баланс USDT: 5000.0000
[MAIN] Telegram-бот запущен в режиме Long Polling
[LOOP] Торговый цикл v2 запущен
[AI] macro-sentinel: blackout=OFF ...
[AI] regime BTCUSDT: TRENDING conf=80 ...
[AI] regime ETHUSDT: ...
[AI] regime SOLUSDT: ...
```

Если вместо успешного баланса OKX - сетевая ошибка, значит IP сервера
попал в OKX-блоклист. Решается сменой VPS или использованием другого
региона у того же провайдера.

## Переход из DRY_RUN в боевой режим

После 24+ часов наблюдений, когда убедились, что:

- бот не падает (нет `[LOOP] Транзиентная ошибка тика`),
- Telegram принимает команды (попробуйте кнопки СТАТИСТИКА / РЕЖИМЫ),
- heartbeat приходит каждые 6 часов,
- регайм-апдейты по всем трём символам идут каждый час без ошибок Groq,

можно перевести бот в боевой режим:

```bash
sudo -u zenith sed -i 's/^DRY_RUN=true/DRY_RUN=false/' /opt/zenith/.env
sudo systemctl restart zenith
```

По умолчанию `config.py::IS_TESTNET = True` - бот торгует на OKX Demo
(5000 USDT виртуально). Переход на mainnet требует отдельного правки
`IS_TESTNET = False` и только после полноценной обкатки.

## Ручная установка через systemd

Полезно, если `install.sh` не удаётся запустить одной командой.

```bash
# 1. Базовые пакеты.
sudo apt-get update
sudo apt-get install -y git curl ca-certificates software-properties-common

# 2. Python 3.11+. На Ubuntu 24.04/26.04 и Debian 13 системный python3
#    уже подходит - ставим только venv-модуль:
sudo apt-get install -y python3 python3-venv
#    На Ubuntu 22.04 - через deadsnakes PPA:
# sudo add-apt-repository -y ppa:deadsnakes/ppa
# sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv
#    На Debian 12:
# sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# 3. Системный пользователь и каталоги.
sudo useradd --system --create-home --home-dir /home/zenith --shell /bin/bash zenith
sudo install -d -o zenith -g zenith /opt/zenith
sudo install -d -o zenith -g zenith /opt/zenith/data

# 4. Код (ветка feat/zenith-control-ultimate - актуальная).
sudo -u zenith git clone --branch feat/zenith-control-ultimate \
    https://github.com/Khyy18/Khy18.git /opt/zenith

# 5. venv и зависимости.
sudo -u zenith python3 -m venv /opt/zenith/.venv
sudo -u zenith /opt/zenith/.venv/bin/pip install --upgrade pip
sudo -u zenith /opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt

# 6. .env (заполните реальными ключами).
sudo -u zenith cp /opt/zenith/.env.example /opt/zenith/.env
sudo -u zenith nano /opt/zenith/.env

# 7. systemd unit.
sudo install -m 644 /opt/zenith/deploy/zenith.service /etc/systemd/system/zenith.service
sudo systemctl daemon-reload
sudo systemctl enable --now zenith.service
```

## Запуск через Docker Compose

Простая альтернатива, если systemd недоступен или хочется изоляции.

```bash
# 1. Клонируем и заполняем .env.
git clone --branch feat/zenith-control-ultimate https://github.com/Khyy18/Khy18.git
cd Khy18
cp .env.example .env
nano .env

# 2. Собираем образ и поднимаем сервис.
docker compose -f deploy/docker-compose.yml up -d --build
```

`docker-compose.yml` монтирует `../trades.db` наружу контейнера, чтобы
SQLite-журнал переживал пересборки. Файл `../.env` читается через
`env_file` и не попадает в образ.

## Мониторинг и управление

Systemd-путь:

```bash
sudo systemctl status zenith            # коротко жив/мёртв
sudo journalctl -u zenith -f            # полный лог в реальном времени
sudo journalctl -u zenith -n 200        # последние 200 строк
sudo journalctl -u zenith --since "1 hour ago" | grep -E "ERROR|ошибка"
sudo systemctl restart zenith           # рестарт (при правке .env, обновлении)
sudo systemctl stop zenith              # остановка
```

Docker-путь:

```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f
docker compose -f deploy/docker-compose.yml restart
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

Для перехода на экспериментальную ветку v2 (7 символов + подсистема
Bollinger mean-reversion, подробности в корневом `README.md`, секция
«v2: Multi-strategy framework»):

```bash
sudo -u zenith git -C /opt/zenith fetch origin
sudo -u zenith git -C /opt/zenith checkout feat/v2-meanrevert
sudo -u zenith /opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt
sudo systemctl restart zenith
```

**Предупреждение.** `feat/v2-meanrevert` - экспериментальная ветка без
полноценного бэктеста. Переключайтесь на неё только после суток
наблюдений в `DRY_RUN=true`, готовьтесь к возможному откату на
`feat/zenith-control-ultimate` одной командой `git checkout`.

Для перехода на ветку v3 (AI-veto gate поверх v2 - Groq-проверка сделки
перед отправкой ордера, подробности в корневом `README.md`, секция
«v3: AI-veto gate»):

```bash
sudo -u zenith git -C /opt/zenith fetch origin
sudo -u zenith git -C /opt/zenith checkout feat/v3-ai-veto
sudo -u zenith /opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt
# Добавить в .env переменную режима gate (по умолчанию shadow - только логирует).
grep -q '^AI_TRADE_GATE_MODE=' /opt/zenith/.env \
    || echo 'AI_TRADE_GATE_MODE=shadow' | sudo tee -a /opt/zenith/.env
sudo systemctl restart zenith
```

**Предупреждение.** `feat/v3-ai-veto` - экспериментальная ветка поверх
`feat/v2-meanrevert` и унаследует все её риски. Стартуйте в
`AI_TRADE_GATE_MODE=shadow`: решения gate логируются, но не применяются -
это даёт возможность увидеть в журнале, какие сделки gate хотел бы
заблокировать, прежде чем переключать на `active`. Откат так же простой:
`git checkout feat/v2-meanrevert` (или `feat/zenith-control-ultimate`
чтобы вернуться на v1) + `systemctl restart zenith`.

Docker:

```bash
git pull --ff-only
docker compose -f deploy/docker-compose.yml up -d --build
```

## Откат

Systemd-путь:

```bash
# Посмотреть последние коммиты:
sudo -u zenith git -C /opt/zenith log --oneline -20
# Откатиться на заведомо рабочий коммит:
sudo -u zenith git -C /opt/zenith reset --hard <commit-sha>
sudo systemctl restart zenith
```

Docker-путь:

```bash
git reset --hard <commit-sha>
docker compose -f deploy/docker-compose.yml up -d --build
```

Если подозреваете повреждение базы сделок, сохраните копию до отката:

```bash
sudo -u zenith cp /opt/zenith/data/trades.db /opt/zenith/data/trades.db.bak
```

Таблицы создаются идемпотентно, бот не удаляет существующие записи.

## Траблшутинг

**`[TG] getUpdates статус 409: Conflict`** - на этом же `TELEGRAM_TOKEN`
где-то ещё работает `getUpdates` (второй инстанс бота). Найдите и
остановите второй процесс, иначе часть команд будет улетать не сюда.

**`[MAIN] Отсутствуют обязательные переменные окружения: ...`** - .env не
заполнен или файл не видится systemd. Проверьте:
`sudo systemctl show zenith -p EnvironmentFile` и содержимое `/opt/zenith/.env`.

**Бот молчит, в логе только `[LOOP] Торговый цикл v2 запущен`** - это норма.
Стратегия пишет `[LOOP] {symbol}: ...` только на ошибках или при открытии/
закрытии позиции. На «happy path» тики молчат. Regime-обновления каждые
60 минут и heartbeat каждые 6 часов - те события, которых стоит ждать.

**Нет открытых сделок за сутки** - это тоже норма для Donchian-стратегии.
Ожидаемая частота - 0.3-1.5 сделки в день на 3 символа суммарно. Тест
имеет смысл вести минимум 72 часа.

**`[MEMORY] Ошибка инициализации БД: unable to open database file`** -
`TRADES_DB_PATH` указывает в несуществующий каталог или без прав записи.
Проверьте `ls -ld /opt/zenith/data` - должен быть `zenith:zenith` с `rwx`.
