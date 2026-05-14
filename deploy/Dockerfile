FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRADES_DB_PATH=/app/data/trades.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent каталог для SQLite. Хранится отдельно от кода, переживает
# `docker compose up --build` и обновления образа.
RUN useradd --system --create-home zenith \
    && mkdir -p /app/data \
    && chown -R zenith:zenith /app

USER zenith

VOLUME ["/app/data"]

CMD ["python", "main.py"]
