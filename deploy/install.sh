#!/usr/bin/env bash
#
# Идемпотентный установщик Zenith-Control Ultimate.
# Поддерживаемые ОС: Ubuntu 22.04/24.04/26.04, Debian 12/13.
# Скрипт НЕ запускает сервис - владельцу нужно сначала заполнить
# /opt/zenith/.env (реальные ключи OKX, Telegram, Groq, NewsAPI).
#

set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "[ERR] Запустите скрипт под root (sudo)." >&2
    exit 1
fi

# --- Определяем дистрибутив ------------------------------------------------
OS_ID="unknown"
OS_VERSION="unknown"
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_VERSION="${VERSION_ID:-unknown}"
fi
echo "[INFO] Обнаружена ОС: ${OS_ID} ${OS_VERSION}"

case "${OS_ID}:${OS_VERSION}" in
    ubuntu:22.04|ubuntu:24.04|ubuntu:26.04|debian:12|debian:13)
        ;;
    *)
        echo "[WARN] Дистрибутив ${OS_ID} ${OS_VERSION} официально не протестирован."
        echo "[WARN] Скрипт продолжит работу на apt-based системе, но возможны расхождения."
        ;;
esac

# --- Общие зависимости -----------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git curl ca-certificates software-properties-common

# --- Python 3.11+ ----------------------------------------------------------
# Код бота совместим с любым Python >= 3.11. Алгоритм:
#   1) Если системный python3 уже >= 3.11 - используем его (Ubuntu 24.04/26.04,
#      Debian 13 поставляют 3.12/3.13 в main).
#   2) Иначе ставим python3.11:
#      - Ubuntu 22.04: через deadsnakes PPA.
#      - Debian 12:    напрямую из main.
#      - Иные apt-based: best effort.
#
# PYTHON_BIN - итоговый путь к интерпретатору, используется ниже.

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    SYS_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
    SYS_MAJOR="${SYS_VER%%.*}"
    SYS_MINOR="${SYS_VER##*.}"
    if [[ "${SYS_MAJOR}" == "3" && "${SYS_MINOR}" -ge 11 ]]; then
        PYTHON_BIN="$(command -v python3)"
        echo "[INFO] Используем системный python3 = ${SYS_VER} (${PYTHON_BIN})"
        # venv-модуль может быть в отдельном пакете (python3.X-venv).
        apt-get install -y "python3-venv" || true
    fi
fi

if [[ -z "${PYTHON_BIN}" ]]; then
    echo "[INFO] Системный python3 старее 3.11, ставим python3.11 вручную"
    if [[ "${OS_ID}" == "ubuntu" && "${OS_VERSION}" == "22.04" ]]; then
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update
        apt-get install -y python3.11 python3.11-venv
    elif [[ "${OS_ID}" == "debian" && "${OS_VERSION}" == "12" ]]; then
        apt-get install -y python3.11 python3.11-venv python3.11-dev
    else
        apt-get install -y python3.11 python3.11-venv || {
            echo "[WARN] Установка python3.11 штатным способом не прошла."
            echo "[WARN] Попробуйте вручную поставить python3.11 из backports/PPA."
        }
    fi
    if command -v python3.11 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3.11)"
    else
        echo "[ERR] Не удалось найти python3.11. Прерываемся."
        exit 2
    fi
fi

echo "[INFO] Интерпретатор для venv: ${PYTHON_BIN}"

# --- Системный пользователь ------------------------------------------------
id -u zenith >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/zenith --shell /bin/bash zenith

# --- Код ------------------------------------------------------------------
# Клонируем под root (у zenith нет прав писать в /opt/), потом отдаём
# владельцем zenith. Это стандартный паттерн для system-user'а без
# write-доступа к родительскому каталогу.
REPO_URL="${REPO_URL:-https://github.com/Khy18/Khy18.git}"
BRANCH="${BRANCH:-feat/zenith-control-ultimate}"
if [[ ! -d /opt/zenith/.git ]]; then
    # Если /opt/zenith есть, но это не git-репо (недозавершённый прошлый
    # запуск, мусор) - сносим, чтобы clone не падал на "not empty".
    if [[ -d /opt/zenith ]]; then
        echo "[INFO] /opt/zenith существует без .git, чистим перед клонированием"
        rm -rf /opt/zenith
    fi
    echo "[INFO] Клонируем ${REPO_URL} (ветка ${BRANCH}) -> /opt/zenith"
    # GIT_TERMINAL_PROMPT=0: git никогда не запрашивает login/password в
    # терминале. Публичный репозиторий клонируется без авторизации; если
    # сервер вернёт 401/403, git быстро упадёт с понятной ошибкой, а не
    # зависнет с "Username for 'https://github.com':" (что особенно вредно
    # при curl | bash).
    # -c credential.helper=: принудительно отключает любой системный
    # credential.helper (keychain, store, libsecret), который мог бы
    # перехватить запрос.
    GIT_TERMINAL_PROMPT=0 git -c credential.helper= \
        clone --branch "${BRANCH}" "${REPO_URL}" /opt/zenith
    chown -R zenith:zenith /opt/zenith
else
    echo "[INFO] Обновляем /opt/zenith (ветка ${BRANCH})"
    sudo -u zenith env GIT_TERMINAL_PROMPT=0 \
        git -C /opt/zenith -c credential.helper= fetch origin "${BRANCH}"
    sudo -u zenith git -C /opt/zenith checkout "${BRANCH}"
    sudo -u zenith env GIT_TERMINAL_PROMPT=0 \
        git -C /opt/zenith -c credential.helper= pull --ff-only origin "${BRANCH}"
fi

# --- Persistent каталог для SQLite ----------------------------------------
# trades.db хранится в /opt/zenith/data (а не рядом с кодом в /opt/zenith),
# чтобы `git pull` / переустановка никогда не трогали БД. memory.py подхватит
# этот путь через TRADES_DB_PATH в .env (или через автодетект /app/data).
# ВАЖНО: создаём ПОСЛЕ git clone, иначе clone падает на непустую директорию.
install -d -o zenith -g zenith /opt/zenith/data

# --- venv и зависимости ----------------------------------------------------
sudo -u zenith "${PYTHON_BIN}" -m venv /opt/zenith/.venv
sudo -u zenith /opt/zenith/.venv/bin/pip install --upgrade pip
sudo -u zenith /opt/zenith/.venv/bin/pip install -r /opt/zenith/requirements.txt

# --- systemd unit ----------------------------------------------------------
install -m 644 /opt/zenith/deploy/zenith.service /etc/systemd/system/zenith.service
systemctl daemon-reload
systemctl enable zenith.service

# --- Финал ----------------------------------------------------------------
cat <<'EOF'

[OK] Zenith-Control Ultimate установлен в /opt/zenith.

Следующие шаги (выполнять ВРУЧНУЮ):
  1. Скопируйте образец и заполните секреты:
         sudo -u zenith cp /opt/zenith/.env.example /opt/zenith/.env
         sudo -u zenith nano /opt/zenith/.env
     Минимально обязательные переменные для EXCHANGE=okx:
         OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE
         TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
         GROQ_API_KEY, NEWS_API_KEY
     Рекомендуется также добавить:
         TRADES_DB_PATH=/opt/zenith/data/trades.db
         DRY_RUN=true  # на первые сутки - paper-trading без реальных ордеров

  2. Запустите сервис:
         sudo systemctl start zenith

  3. Смотрите журнал в реальном времени:
         sudo journalctl -u zenith -f

  4. Когда убедитесь, что всё работает (~24 часа наблюдений):
         sudo -u zenith sed -i 's/^DRY_RUN=true/DRY_RUN=false/' /opt/zenith/.env
         sudo systemctl restart zenith

ВАЖНО: не запускайте бот на том же TELEGRAM_TOKEN, который уже используется
другим процессом (локально или на другом сервере). Telegram выдаёт getUpdates
только одному клиенту за раз - второй получит HTTP 409 Conflict и потеряет
команды из чата.
EOF
