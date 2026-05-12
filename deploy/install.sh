#!/usr/bin/env bash
#
# Идемпотентный установщик Zenith-Control Ultimate для Ubuntu 22.04 и Debian 12.
# Скрипт НЕ запускает сервис - владельцу нужно сначала заполнить /opt/zenith/.env.
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
    ubuntu:22.04|debian:12)
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

# --- python3.11 + venv -----------------------------------------------------
if [[ "${OS_ID}" == "ubuntu" && "${OS_VERSION}" == "22.04" ]]; then
    command -v python3.11 >/dev/null 2>&1 || {
        echo "[INFO] python3.11 не найден, подключаем deadsnakes PPA"
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update
        apt-get install -y python3.11 python3.11-venv
    }
elif [[ "${OS_ID}" == "debian" && "${OS_VERSION}" == "12" ]]; then
    apt-get install -y python3.11 python3.11-venv python3.11-dev
else
    apt-get install -y python3.11 python3.11-venv || {
        echo "[WARN] Установка python3.11 штатным способом не прошла."
        echo "[WARN] Попробуйте вручную поставить python3.11 из backports/PPA."
    }
fi

# --- Системный пользователь ------------------------------------------------
id -u zenith >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/zenith --shell /bin/bash zenith
install -d -o zenith -g zenith /opt/zenith

# --- Код ------------------------------------------------------------------
REPO_URL="${REPO_URL:-https://github.com/Khy18/Khy18.git}"
if [[ ! -d /opt/zenith/.git ]]; then
    echo "[INFO] Клонируем ${REPO_URL} -> /opt/zenith"
    sudo -u zenith git clone "${REPO_URL}" /opt/zenith
else
    echo "[INFO] Обновляем /opt/zenith"
    sudo -u zenith git -C /opt/zenith pull --ff-only
fi

# --- venv и зависимости ----------------------------------------------------
sudo -u zenith python3.11 -m venv /opt/zenith/.venv
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
  2. Запустите сервис:
         sudo systemctl start zenith
  3. Смотрите журнал в реальном времени:
         sudo journalctl -u zenith -f

ВАЖНО: без корректного .env (BYBIT_API_KEY, BYBIT_API_SECRET, TELEGRAM_TOKEN,
TELEGRAM_CHAT_ID, GEMINI_API_KEY, NEWS_API_KEY) сервис не запустится.
EOF
